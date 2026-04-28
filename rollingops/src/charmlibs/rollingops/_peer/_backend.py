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

import logging
from collections.abc import Callable
from typing import Any

from ops import Object, Relation, Unit
from ops.charm import (
    CharmBase,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import EventBase

from charmlibs import pathops
from charmlibs.rollingops._common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsInvalidLockRequestError,
    RollingOpsNoRelationError,
)
from charmlibs.rollingops._common._models import (
    Operation,
    OperationResult,
    RollingOpsStatus,
    RunWithLockOutcome,
    RunWithLockStatus,
)
from charmlibs.rollingops._peer._models import (
    PeerAppLock,
    PeerUnitOperations,
    iter_peer_units,
    pick_oldest_completed,
    pick_oldest_request,
)
from charmlibs.rollingops._peer._worker import PeerRollingOpsAsyncWorker

logger = logging.getLogger(__name__)


class _PeerRollingOpsBackend(Object):  # pyright: ignore[reportUnusedClass]
    """Manage rolling operations using the peer-relation backend.

    This backend stores operation queues in the peer relation and relies
    on the leader unit to schedule lock grants across units. Once a unit
    is granted the lock, it executes its queued operation locally.

    The peer backend acts as both the primary backend when etcd is not
    available and as the durable fallback state used to continue
    processing when etcd-backed execution fails.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        callback_targets: dict[str, Callable[..., Any]],
        base_dir: pathops.LocalPath,
    ):
        """Initialize the peer-backed rolling-ops backend.

        Args:
            charm: The charm instance owning this backend.
            relation_name: Name of the peer relation used to store lock and
                operation state.
            callback_targets: Mapping from callback identifiers to callables
                executed when this unit is granted the lock.
            base_dir: base directory where all files related to rollingops will be written.
        """
        super().__init__(charm, 'peer-rolling-ops-manager')
        self._charm = charm
        self.relation_name = relation_name
        self.callback_targets = callback_targets
        self.worker = PeerRollingOpsAsyncWorker(
            charm, relation_name=relation_name, base_dir=base_dir
        )

        self.framework.observe(
            charm.on[self.relation_name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            charm.on[self.relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(charm.on.leader_elected, self._process_locks)

    @property
    def _relation(self) -> Relation | None:
        """Return the peer relation used for lock and operation state."""
        return self.model.get_relation(self.relation_name)

    def _lock(self) -> PeerAppLock:
        """Return the shared application-level peer lock.

        This lock is stored in the peer relation application databag and is
        used by the leader to grant execution rights to one unit at a time.
        """
        return PeerAppLock(self.model, self.relation_name)

    def _operations(self, unit: Unit) -> PeerUnitOperations:
        """Return the peer-backed operation queue for a unit.

        Args:
            unit: The unit whose operation queue should be accessed.

        Returns:
            A helper for reading and updating that unit's queued operations.
        """
        return PeerUnitOperations(self.model, self.relation_name, unit)

    def enqueue_operation(self, operation: Operation) -> None:
        """Persist an operation in the current unit's peer-backed queue.

        Args:
            operation: The operation to enqueue.

        Raises:
            RollingOpsInvalidLockRequestError: If the operation could not be
                persisted due to invalid or undecodable queue state.
            RollingOpsNoRelationError: If the peer relation is not available.
        """
        try:
            self._operations(self.model.unit).request(operation)
        except (RollingOpsDecodingError, ValueError) as e:
            logger.error('Failed to create operation: %s', e)
            raise RollingOpsInvalidLockRequestError('Failed to create the lock request') from e
        except RollingOpsNoRelationError as e:
            logger.debug('No %s peer relation yet.', self.relation_name)
            raise e

    def ensure_processing(self) -> None:
        """Trigger peer-based scheduling if the current unit is leader.

        In the peer backend, scheduling decisions are made only by the
        leader unit. Non-leader units do not actively process locks.
        """
        if self.model.unit.is_leader():
            self._process_locks()

    def has_pending_work(self) -> bool:
        """Return whether the current unit has pending peer-managed work."""
        return self._operations(self.model.unit).has_pending_work()

    def _on_rollingops_lock_granted(self, event: EventBase) -> None:
        """Handler of the custom hook rollingops_lock_granted.

        The custom hook is triggered by a background process.
        """
        if not self._relation:
            return
        lock = self._lock()
        operations = self._operations(self.model.unit)
        if operations.should_run(lock):
            self._on_run_with_lock()
        self._process_locks()

    def _on_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Leader cleanup: if a departing unit was granted a lock, clear the grant.

        This prevents deadlocks when the granted unit leaves the relation.
        """
        if not self.model.unit.is_leader():
            return
        if unit := event.departing_unit:
            lock = self._lock()
            if lock.is_granted(unit.name):
                lock.release()
        self._process_locks()

    def _on_relation_changed(self, _: RelationChangedEvent) -> None:
        """React to peer relation changes.

        The leader re-runs scheduling whenever peer relation state changes.
        Non-leader units only check whether they should execute an operation
        that has already been granted to them.
        """
        if self.model.unit.is_leader():
            self._process_locks()
            return

        lock = self._lock()
        operations = self._operations(self.model.unit)
        if operations.should_run(lock):
            self._on_run_with_lock()

    def _valid_peer_unit_names(self) -> set[str]:
        """Return all unit names currently participating in the peer relation."""
        if not self._relation:
            return set()
        names = {u.name for u in self._relation.units}
        names.add(self.model.unit.name)
        return names

    def _release_stale_grant(self) -> None:
        """Ensure granted_unit refers to a unit currently on the peer relation."""
        if not self._relation:
            return

        lock = self._lock()
        granted_unit = lock.granted_unit
        if not granted_unit:
            return

        valid_units = self._valid_peer_unit_names()
        if granted_unit not in valid_units:
            logger.warning(
                'granted_unit=%s is not in current peer units; releasing stale grant.',
                granted_unit,
            )
            lock.release()

    def _process_locks(self, _: EventBase | None = None) -> None:
        """Process locks.

        This method is only executed by the leader unit.
        It effectively releases the lock and triggers scheduling.
        """
        if not self.model.unit.is_leader():
            return

        lock = self._lock()

        for unit in iter_peer_units(self.model, self.relation_name):
            operations = self._operations(unit)
            if not operations.is_peer_managed():
                continue
            if operations.should_release(lock):
                lock.release()
                break

        self._release_stale_grant()

        if lock.granted_unit:
            logger.info(
                'Current granted_unit=%s. No new unit will be scheduled.',
                lock.granted_unit,
            )
            return

        self._schedule(lock)

    def _schedule(self, lock: PeerAppLock) -> None:
        """Select and grant the next lock based on priority and queue state.

        This method iterates over all locks associated with the relation and
        determines which unit should receive the lock next.

        Priority order:
        1. Units in RETRY_HOLD state are immediately granted the lock.
        2. Units in REQUEST state are considered next (oldest request first).
        3. Units in RETRY_RELEASE state are considered last (oldest completed first).

        If no eligible lock is found, no action is taken.

        Once a lock is selected, it is granted via `_grant_lock`.
        """
        logger.info('Starting scheduling.')

        pending_requests: list[PeerUnitOperations] = []
        pending_retries: list[PeerUnitOperations] = []

        for unit in iter_peer_units(self.model, self.relation_name):
            operations = self._operations(unit)

            if not operations.is_peer_managed():
                continue

            if operations.is_retry_hold():
                self._grant_lock(lock, operations.unit.name)
                return

            if operations.is_waiting():
                pending_requests.append(operations)
            elif operations.is_waiting_retry():
                pending_retries.append(operations)

        selected = None
        if pending_requests:
            selected = pick_oldest_request(pending_requests)
        elif pending_retries:
            selected = pick_oldest_completed(pending_retries)

        if selected is None:
            logger.info('No pending lock requests. Lock was not granted to any unit.')
            return

        self._grant_lock(lock, selected)

    def _grant_lock(self, lock: PeerAppLock, unit_name: str) -> None:
        """Grant the lock to the selected unit.

        Once the lock is granted, the selected unit becomes eligible to
        execute its next queued operation. If the selected unit is the local
        unit (leader), its worker process is started to trigger execution.

        Args:
            lock: The peer lock instance to grant.
            unit_name: Name of the unit receiving the lock grant.
        """
        lock.grant(unit_name)
        logger.info('Lock granted to unit=%s.', unit_name)

        if unit_name == self.model.unit.name:
            self.worker.start()

    def request_async_lock(
        self,
        callback_id: str,
        kwargs: dict[str, Any] | None = None,
        max_retry: int | None = None,
    ) -> None:
        """Enqueue a rolling operation and request the distributed lock.

        This method appends an operation (identified by callback_id and kwargs) to the
        calling unit's FIFO queue stored in the peer relation databag and marks the unit as
        requesting the lock. It does not execute the operation directly.

        Args:
            callback_id: Identifier for the callback to execute when this unit is granted
                the lock. Must be a non-empty string and must exist in the manager's
                callback registry.
            kwargs: Keyword arguments to pass to the callback when executed. If omitted,
                an empty dict is used. Must be JSON-serializable because it is stored
                in Juju relation databags.
            max_retry: Retry limit for this operation. None means unlimited retries.
                0 means no retries (drop immediately on first failure). Must be >= 0
                when provided.

        Raises:
            RollingOpsInvalidLockRequestError: If any input is invalid (e.g. unknown callback_id,
                non-dict kwargs, non-serializable kwargs, negative max_retry).
            RollingOpsNoRelationError: If the peer relation does not exist.
        """
        if callback_id not in self.callback_targets:
            raise RollingOpsInvalidLockRequestError(f'Unknown callback_id: {callback_id}')

        try:
            if kwargs is None:
                kwargs = {}
            operation = Operation.create(callback_id, kwargs, max_retry)
            operations = self._operations(self.model.unit)
            operations.request(operation)

        except (RollingOpsDecodingError, ValueError) as e:
            logger.error('Failed to create operation: %s', e)
            raise RollingOpsInvalidLockRequestError('Failed to create the lock request') from e
        except RollingOpsNoRelationError as e:
            logger.debug('No %s peer relation yet.', self.relation_name)
            raise e

        if self.model.unit.is_leader():
            self._process_locks()

    def _on_run_with_lock(self) -> None:
        """Execute the current head operation if this unit holds the distributed lock.

        - If this unit does not currently hold the lock grant, no operation is run.
        - If this unit holds the grant but has no queued operation, lock is released.
        - Otherwise, the operation's callback is looked up by `callback_id` and
            invoked with the operation kwargs.
        """
        lock = self._lock()
        operations = self._operations(self.model.unit)

        if not lock.is_granted(self.model.unit.name):
            logger.debug('Lock is not granted. Operation will not run.')
            return

        if not (operation := operations.get_current()):
            logger.debug('There is no operation to run.')
            operations.finish(OperationResult.RELEASE)
            return

        if not (callback := self.callback_targets.get(operation.callback_id)):
            logger.error(
                'Operation %s target was not found. Releasing operation without retry.',
                operation.callback_id,
            )
            operations.finish(OperationResult.RELEASE)
            return
        logger.info(
            'Executing callback_id=%s, attempt=%s', operation.callback_id, operation.attempt
        )
        try:
            result = callback(**operation.kwargs)
        except Exception as e:
            logger.exception('Operation failed: %s: %s', operation.callback_id, e)
            result = OperationResult.RETRY_RELEASE

        logger.info('Operation %s executed with result %s.', operation.callback_id, result)
        operations.finish(result)

    def mirror_outcome(self, outcome: RunWithLockOutcome) -> None:
        """Apply the execution result to the mirrored peer queue.

        This keeps the peer standby queue aligned with the backend that
        actually executed the operation.

        Args:
            outcome: The etcd execution outcome to mirror.

        Raises:
            RollingOpsDecodingError: If theres is an inconsistency found.
        """
        match outcome.status:
            case RunWithLockStatus.NOT_GRANTED:
                logger.info('Skipping mirror: etcd lock was not granted.')
                return

            case RunWithLockStatus.NO_OPERATION:
                if not self._operations(self.model.unit).has_pending_work():
                    logger.info('Skipping mirror: no operation.')
                    return
                raise RollingOpsDecodingError(
                    'Mismatch between the etcd and peer operation queue.'
                )

            case (
                RunWithLockStatus.MISSING_CALLBACK
                | RunWithLockStatus.EXECUTED
                | RunWithLockStatus.EXECUTED_NOT_COMMITTED
            ):
                self._operations(self.model.unit).mirror_result(outcome.op_id, outcome.result)  # type: ignore[reportArgumentType]
            case _:
                raise RollingOpsDecodingError(
                    f'Unsupported run-with-lock outcome: {outcome.status}'
                )

    def get_status(self) -> RollingOpsStatus:
        """Return the current rolling-ops status for this unit in peer mode.

        Status is derived from the local unit's peer-backed operation queue
        and from the shared peer lock state.

        Returned values:
            - NOT_READY: the peer relation does not exist
            - GRANTED: the current unit holds the peer lock
            - WAITING: the current unit has queued work but does not hold the lock
            - IDLE: the current unit has no pending work

        Returns:
            The current rolling-ops status for this unit.
        """
        if self._relation is None:
            return RollingOpsStatus.NOT_READY

        lock = self._lock()
        operations = self._operations(self.model.unit)

        if lock.is_granted(self.model.unit.name):
            return RollingOpsStatus.GRANTED

        if operations.has_pending_work():
            return RollingOpsStatus.WAITING

        return RollingOpsStatus.IDLE
