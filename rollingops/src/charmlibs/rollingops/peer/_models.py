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

import json
import logging
from collections.abc import Iterator
from datetime import datetime
from enum import StrEnum
from typing import Any

from ops import Model, RelationDataContent, Unit

from charmlibs.rollingops.common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsNoRelationError,
)
from charmlibs.rollingops.common._models import Operation, now_timestamp_str, parse_timestamp

logger = logging.getLogger(__name__)


class OperationQueue:
    """In-memory FIFO queue of Operations with encode/decode helpers for storing in a databag."""

    def __init__(self, operations: list[Operation] | None = None):
        self.operations: list[Operation] = list(operations or [])

    def __len__(self) -> int:
        """Return the number of operations in the queue."""
        return len(self.operations)

    @property
    def empty(self) -> bool:
        """Return True if there are no queued operations."""
        return not self.operations

    def peek(self) -> Operation | None:
        """Return the first operation in the queue if it exists."""
        return self.operations[0] if self.operations else None

    def _peek_last(self) -> Operation | None:
        """Return the last operation in the queue if it exists."""
        return self.operations[-1] if self.operations else None

    def dequeue(self) -> Operation | None:
        """Drop the first operation in the queue if it exists and return it."""
        return self.operations.pop(0) if self.operations else None

    def increase_attempt(self) -> None:
        """Increment the attempt counter for the head operation and persist it."""
        if self.empty:
            return
        self.operations[0].increase_attempt()

    def enqueue_lock_request(
        self, callback_id: str, kwargs: dict[str, Any], max_retry: int | None = None
    ) -> None:
        """Append operation only if it is not equal to the last enqueued operation."""
        operation = Operation.create(callback_id, kwargs, max_retry=max_retry)

        last_operation = self._peek_last()
        if last_operation is not None and last_operation == operation:
            return
        self.operations.append(operation)

    def to_string(self) -> str:
        """Encode entire queue to a single string."""
        items = [op.to_string() for op in self.operations]
        return json.dumps(items, separators=(',', ':'))

    @classmethod
    def from_string(cls, data: str) -> 'OperationQueue':
        """Decode queue from a string.

        Raises:
            RollingOpsDecodingError: if data cannot be deserialized.
        """
        if not data:
            return cls()

        try:
            items = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(
                'Failed to deserialize data to create an OperationQueue from %s: %s', data, e
            )
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an OperationQueue.'
            ) from e
        if not isinstance(items, list) or not all(isinstance(s, str) for s in items):  # type: ignore[reportUnknownVariableType]
            raise RollingOpsDecodingError(
                'OperationQueue string must decode to a JSON list of strings.'
            )

        operations = [Operation.from_string(s) for s in items]  # type: ignore[reportUnknownVariableType]
        return cls(operations)


class LockIntent(StrEnum):
    """Unit-level lock intents stored in unit databags."""

    REQUEST = 'request'
    RETRY_RELEASE = 'retry-release'
    RETRY_HOLD = 'retry-hold'
    IDLE = 'idle'


class Lock:
    """State machine view over peer relation databags for a single unit.

    This class is the only component that should directly read/write the peer relation
    databags for lock state, queue state, and grant state.

    Important:
      - All relation databag values are strings.
      - This class updates both unit databags and app databags, which triggers
        relation-changed events.
    """

    def __init__(self, model: Model, relation_name: str, unit: Unit):
        if not model.get_relation(relation_name):
            # TODO: defer caller in this case (probably just fired too soon).
            raise RollingOpsNoRelationError()
        self.relation = model.get_relation(relation_name)
        self.unit = unit
        self.app = model.app

    @property
    def _app_data(self) -> RelationDataContent:
        return self.relation.data[self.app]  # type: ignore[reportOptionalMemberAccess]

    @property
    def _unit_data(self) -> RelationDataContent:
        return self.relation.data[self.unit]  # type: ignore[reportOptionalMemberAccess]

    @property
    def _operations(self) -> OperationQueue:
        return OperationQueue.from_string(self._unit_data.get('operations', ''))

    @property
    def _state(self) -> str:
        return self._unit_data.get('state', '')

    def request(
        self, callback_id: str, kwargs: dict[str, Any], max_retry: int | None = None
    ) -> None:
        """Enqueue an operation and mark this unit as requesting the lock.

        Args:
          callback_id: identifies which callback to execute.
          kwargs: dict of callback kwargs.
          max_retry: None -> unlimited retries, else explicit integer.
        """
        queue = self._operations

        previous_length = len(queue)
        queue.enqueue_lock_request(callback_id, kwargs, max_retry)
        if previous_length == len(queue):
            logger.info(
                'Operation %s not added to the queue. It already exists in the back of the queue.',
                callback_id,
            )
            return

        if len(queue) == 1:
            self._unit_data.update({'state': LockIntent.REQUEST})

        self._unit_data.update({'operations': queue.to_string()})
        logger.info('Operation %s added to the queue.', callback_id)

    def _set_retry(self, intent: LockIntent) -> None:
        """Mark the given retry intent on the head operation.

        If max_retry is reached, the head operation is dropped via complete().
        """
        self._increase_attempt()
        if self._is_max_retry_reached():
            logger.warning('Operation max retry reached. Dropping.')
            self.complete()
            return
        self._unit_data.update({
            'executed_at': now_timestamp_str(),
            'state': intent,
        })

    def retry_release(self) -> None:
        """Indicate that the operation should be retried but the lock should be released."""
        self._set_retry(LockIntent.RETRY_RELEASE)

    def retry_hold(self) -> None:
        """Indicate that the operation should be retried but the lock should be kept."""
        self._set_retry(LockIntent.RETRY_HOLD)

    def complete(self) -> None:
        """Mark the head operation as completed successfully, pop it from the queue.

        Update unit state depending on whether more operations remain.
        """
        queue = self._operations
        queue.dequeue()
        next_state = LockIntent.REQUEST if queue.peek() else LockIntent.IDLE

        self._unit_data.update({
            'state': next_state,
            'operations': queue.to_string(),
            'executed_at': now_timestamp_str(),
        })

    def release(self) -> None:
        """Clear the application-level grant."""
        self._app_data.update({'granted_unit': '', 'granted_at': ''})

    def grant(self) -> None:
        """Grant a lock to a unit."""
        self._app_data.update({
            'granted_unit': str(self.unit.name),
            'granted_at': now_timestamp_str(),
        })

    def is_granted(self) -> bool:
        """Return True if the unit holds the lock."""
        granted_unit = self._app_data.get('granted_unit', '')
        return granted_unit == str(self.unit.name)

    def should_run(self) -> bool:
        """Return True if the lock has been granted to the unit and it is time to run."""
        return self.is_granted() and not self._unit_executed_after_grant()

    def should_release(self) -> bool:
        """Return True if the unit finished executing the callback and should be released."""
        return self.is_completed() or self._unit_executed_after_grant()

    def is_waiting(self) -> bool:
        """Return True if this unit is waiting for a lock to be granted."""
        return self._state == LockIntent.REQUEST and not self.is_granted()

    def is_completed(self) -> bool:
        """Return True if this unit is completed callback but still has the grant.

        Transitional state in which the unit is waiting for the leader to release the lock.
        """
        return self._state == LockIntent.IDLE and self.is_granted()

    def is_retry(self) -> bool:
        """Return True if this unit requested retry but still has the grant.

        Transitional state in which the unit is waiting for the leader to release the lock.
        """
        unit_intent = self._state
        return (
            unit_intent == LockIntent.RETRY_RELEASE or unit_intent == LockIntent.RETRY_HOLD
        ) and self.is_granted()

    def is_waiting_retry(self) -> bool:
        """Return True if the unit requested retry and is waiting for lock to be granted."""
        return self._state == LockIntent.RETRY_RELEASE and not self.is_granted()

    def is_retry_hold(self) -> bool:
        """Return True if the unit requested retry and wants to keep the lock."""
        return self._state == LockIntent.RETRY_HOLD and not self.is_granted()

    def get_current_operation(self) -> Operation | None:
        """Return the head operation for this unit, if any."""
        return self._operations.peek()

    def _is_max_retry_reached(self) -> bool:
        """Return True if the head operation exceeded its max_retry (unless max_retry is None)."""
        if not (operation := self.get_current_operation()):
            return True
        return operation.is_max_retry_reached()

    def _increase_attempt(self) -> None:
        """Increment the attempt counter for the head operation and persist it."""
        q = self._operations
        q.increase_attempt()
        self._unit_data.update({'operations': q.to_string()})

    def get_last_completed(self) -> datetime | None:
        """Get the time the unit requested a retry of the head operation."""
        if timestamp_str := self._unit_data.get('executed_at', ''):
            return parse_timestamp(timestamp_str)
        return None

    def get_requested_at(self) -> datetime | None:
        """Get the time the head operation was requested at."""
        if not (operation := self.get_current_operation()):
            return None
        return operation.requested_at

    def _unit_executed_after_grant(self) -> bool:
        """Returns True if the unit executed its callback after the lock was granted."""
        granted_at = parse_timestamp(self._app_data.get('granted_at', ''))
        executed_at = parse_timestamp(self._unit_data.get('executed_at', ''))

        if granted_at is None or executed_at is None:
            return False
        return executed_at > granted_at


def pick_oldest_completed(locks: list[Lock]) -> Lock | None:
    """Choose the retry lock with the oldest executed_at timestamp."""
    selected = None
    oldest_timestamp = None

    for lock in locks:
        timestamp = lock.get_last_completed()
        if not timestamp:
            continue

        if oldest_timestamp is None or timestamp < oldest_timestamp:
            oldest_timestamp = timestamp
            selected = lock

    return selected


def pick_oldest_request(locks: list[Lock]) -> Lock | None:
    """Choose the lock with the oldest head operation."""
    selected = None
    oldest_request = None

    for lock in locks:
        timestamp = lock.get_requested_at()
        if not timestamp:
            continue

        if oldest_request is None or timestamp < oldest_request:
            oldest_request = timestamp
            selected = lock

    return selected


class LockIterator:
    """Iterator over Lock objects for each unit present on the peer relation."""

    def __init__(self, model: Model, relation_name: str):
        relation = model.relations[relation_name][0]
        units = relation.units
        units.add(model.unit)
        self._model = model
        self._units = units
        self._relation_name = relation_name

    def __iter__(self) -> Iterator[Lock]:
        """Yields a lock for each unit we can find on the relation."""
        for unit in self._units:
            yield Lock(self._model, self._relation_name, unit=unit)
