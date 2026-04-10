# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Models for peer-relation rollingops."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ops import Model, Unit

from charmlibs.rollingops.common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsNoRelationError,
)
from charmlibs.rollingops.common._models import (
    Operation,
    OperationQueue,
    OperationResult,
    UnitBackendState,
)
from charmlibs.rollingops.common._utils import datetime_to_str, now_timestamp, parse_timestamp

logger = logging.getLogger(__name__)


class LockIntent(StrEnum):
    """Unit-level lock intents stored in unit databags."""

    REQUEST = 'request'
    RETRY_RELEASE = 'retry-release'
    RETRY_HOLD = 'retry-hold'
    IDLE = 'idle'


@dataclass
class PeerAppData:
    """Application-scoped peer relation data."""

    granted_unit: str = ''
    granted_at: str = ''

    @property
    def granted_at_dt(self) -> datetime | None:
        """Return the grant timestamp as a datetime, if present."""
        return parse_timestamp(self.granted_at)

    @granted_at_dt.setter
    def granted_at_dt(self, value: datetime | None) -> None:
        """Store the grant timestamp from a datetime."""
        self.granted_at = datetime_to_str(value) if value is not None else ''


@dataclass
class PeerUnitData:
    """Unit-scoped peer relation data."""

    state: str = ''
    operations: str = ''
    executed_at: str = ''

    @property
    def intent(self) -> LockIntent:
        """Return the unit state as a LockIntent."""
        return LockIntent(self.state) if self.state else LockIntent.IDLE

    @intent.setter
    def intent(self, value: LockIntent) -> None:
        """Store the unit state from a LockIntent."""
        self.state = value

    @property
    def queue(self) -> OperationQueue:
        """Return the stored operation queue."""
        return OperationQueue.from_string(self.operations)

    @queue.setter
    def queue(self, value: OperationQueue) -> None:
        """Store the operation queue."""
        self.operations = value.to_string()

    @property
    def executed_at_dt(self) -> datetime | None:
        """Return the execution timestamp as a datetime, if present."""
        return parse_timestamp(self.executed_at)

    @executed_at_dt.setter
    def executed_at_dt(self, value: datetime | None) -> None:
        """Store the execution timestamp from a datetime."""
        self.executed_at = datetime_to_str(value) if value is not None else ''


class PeerAppLock:
    """Application-scoped distributed lock state."""

    def __init__(self, model: Model, relation_name: str):
        relation = model.get_relation(relation_name)
        if relation is None:
            raise RollingOpsNoRelationError()

        self._relation = relation
        self._app = model.app

    def _load(self) -> PeerAppData:
        return self._relation.load(PeerAppData, self._app, decoder=lambda s: s)

    def _save(self, data: PeerAppData) -> None:
        self._relation.save(data, self._app, encoder=str)

    @property
    def granted_unit(self) -> str:
        """Return the unit name currently holding the grant, if any."""
        return self._load().granted_unit

    @property
    def granted_at(self) -> datetime | None:
        """Return the timestamp when the grant was issued, if any."""
        return self._load().granted_at_dt

    def grant(self, unit_name: str) -> None:
        """Grant the lock to the provided unit."""
        data = self._load()
        data.granted_unit = unit_name
        data.granted_at_dt = now_timestamp()
        self._save(data)

    def release(self) -> None:
        """Clear the current grant."""
        data = self._load()
        data.granted_unit = ''
        data.granted_at_dt = None
        self._save(data)

    def is_granted(self, unit_name: str) -> bool:
        """Return whether the provided unit currently holds the grant."""
        return self.granted_unit == unit_name


class PeerUnitOperations:
    """Unit-scoped queued operations and execution state."""

    def __init__(self, model: Model, relation_name: str, unit: Unit):
        relation = model.get_relation(relation_name)
        if relation is None:
            raise RollingOpsNoRelationError()

        self._relation = relation
        self.unit = unit
        self._backend_state = UnitBackendState(model, relation_name, unit)

    def _load(self) -> PeerUnitData:
        return self._relation.load(PeerUnitData, self.unit, decoder=lambda s: s)

    def _save(self, data: PeerUnitData) -> None:
        self._relation.save(data, self.unit, encoder=str)

    def is_peer_managed(self) -> bool:
        """Return whether the peer backend should process this unit's queue."""
        return self._backend_state.is_peer_managed()

    @property
    def intent(self) -> LockIntent:
        """Return the current unit intent."""
        return self._load().intent

    @property
    def executed_at(self) -> datetime | None:
        """Return the last execution timestamp for this unit."""
        return self._load().executed_at_dt

    @property
    def queue(self) -> OperationQueue:
        return self._load().queue

    def get_current(self) -> Operation | None:
        """Return the head operation, if any."""
        return self._load().queue.peek()

    def has_pending_work(self) -> bool:
        """Return whether this unit still has queued work."""
        return self.get_current() is not None

    def request(self, operation: Operation) -> None:
        """Enqueue an operation and mark this unit as requesting the lock."""
        data = self._load()
        queue = data.queue

        previous_length = len(queue)
        queue.enqueue(operation)
        added = len(queue) != previous_length
        if not added:
            logger.info(
                'Operation %s not added to the peer queue. '
                'It already exists in the back of the queue.',
                operation.callback_id,
            )
            return

        data.queue = queue
        if len(queue) == 1:
            data.intent = LockIntent.REQUEST
        self._save(data)
        logger.info('Operation %s added to the peer queue.', operation.callback_id)

    def finish(self, result: OperationResult) -> None:
        """Persist the result of executing the current operation."""
        data = self._load()
        self._apply_result_to_data(data, result)
        self._save(data)

    def _apply_result_to_data(
        self,
        data: PeerUnitData,
        result: OperationResult,
    ) -> None:
        queue = data.queue
        operation = queue.peek()

        if operation is None:
            data.intent = LockIntent.IDLE
            data.executed_at_dt = now_timestamp()
            return

        match result:
            case OperationResult.RETRY_HOLD:
                queue.increase_attempt()
                operation = queue.peek()
                if operation is None or operation.is_max_retry_reached():
                    logger.warning('Operation max retry reached. Dropping.')
                    queue.dequeue()
                    data.intent = LockIntent.REQUEST if queue.peek() else LockIntent.IDLE
                else:
                    data.intent = LockIntent.RETRY_HOLD

            case OperationResult.RETRY_RELEASE:
                queue.increase_attempt()
                operation = queue.peek()
                if operation is None or operation.is_max_retry_reached():
                    logger.warning('Operation max retry reached. Dropping.')
                    queue.dequeue()
                    data.intent = LockIntent.REQUEST if queue.peek() else LockIntent.IDLE
                else:
                    data.intent = LockIntent.RETRY_RELEASE
            case _:
                queue.dequeue()
                data.intent = LockIntent.REQUEST if queue.peek() else LockIntent.IDLE

        data.queue = queue
        data.executed_at_dt = now_timestamp()

    def should_run(self, lock: PeerAppLock) -> bool:
        """Return whether this unit should execute now."""
        return (
            self.is_peer_managed()
            and lock.is_granted(self.unit.name)
            and not self._executed_after_grant(lock)
        )

    def should_release(self, lock: PeerAppLock) -> bool:
        """Return whether this unit should release the lock."""
        return (self.is_peer_managed() and self.is_completed(lock)) or self._executed_after_grant(
            lock
        )

    def is_waiting(self) -> bool:
        """Return whether this unit is waiting for a fresh grant."""
        return self.is_peer_managed() and self.intent == LockIntent.REQUEST

    def is_waiting_retry(self) -> bool:
        """Return whether this unit is waiting for a retry after releasing."""
        return self.is_peer_managed() and self.intent == LockIntent.RETRY_RELEASE

    def is_retry_hold(self) -> bool:
        """Return whether this unit wants to retry while keeping priority."""
        return self.is_peer_managed() and self.intent == LockIntent.RETRY_HOLD

    def is_retry(self, lock: PeerAppLock) -> bool:
        """Return whether this unit is in a retry state and currently granted."""
        return (
            self.is_peer_managed()
            and self.intent
            in {
                LockIntent.RETRY_RELEASE,
                LockIntent.RETRY_HOLD,
            }
            and lock.is_granted(self.unit.name)
        )

    def is_completed(self, lock: PeerAppLock) -> bool:
        """Return whether this unit completed and still holds the grant."""
        return (
            self.is_peer_managed()
            and self.intent == LockIntent.IDLE
            and lock.is_granted(self.unit.name)
        )

    def requested_at(self) -> datetime | None:
        """Return the timestamp of the current operation request, if any."""
        operation = self.get_current()
        return operation.requested_at if operation is not None else None

    def _executed_after_grant(self, lock: PeerAppLock) -> bool:
        """Return whether execution happened after the current grant."""
        granted_at = lock.granted_at
        executed_at = self.executed_at
        if granted_at is None or executed_at is None:
            return False
        return executed_at > granted_at

    def mirror_result(self, op_id: str, result: OperationResult) -> None:
        """Apply an execution result to the mirrored peer queue.

        This keeps the peer copy aligned with the backend that actually executed
        the operation.

        If the current mirrored head no longer matches the finalized operation,
        this method does nothing.
        """
        data = self._load()
        current = data.queue.peek()

        if current is None:
            logger.warning('Cannot mirror finalized operation: peer queue is empty.')
            return

        if current.op_id != op_id:
            logger.warning(
                'Cannot mirror finalized operation: peer head op_id=%s '
                'does not match finalized op_id=%s.',
                current.op_id,
                op_id,
            )
            raise RollingOpsDecodingError('Inconsistent operation found.')

        self._apply_result_to_data(data, result)
        self._save(data)


def iter_peer_units(model: Model, relation_name: str) -> Iterator[Unit]:
    """Yield all units currently participating in the peer relation, including self."""
    relation = model.get_relation(relation_name)
    if relation is None:
        raise RollingOpsNoRelationError()

    units = set(relation.units)
    units.add(model.unit)

    yield from units


def pick_oldest_completed(operations_list: list[PeerUnitOperations]) -> str | None:
    """Return the name of the unit with the oldest executed_at timestamp."""
    selected = None
    oldest = None

    for operations in operations_list:
        timestamp = operations.executed_at
        if timestamp is None:
            continue
        if oldest is None or timestamp < oldest:
            oldest = timestamp
            selected = operations

    return selected.unit.name if selected is not None else None


def pick_oldest_request(operations_list: list[PeerUnitOperations]) -> str | None:
    """Return the name of the unit with the oldest head operation."""
    selected = None
    oldest = None

    for operations in operations_list:
        timestamp = operations.requested_at()
        if timestamp is None:
            continue
        if oldest is None or timestamp < oldest:
            oldest = timestamp
            selected = operations

    return selected.unit.name if selected is not None else None
