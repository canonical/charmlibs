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

"""Rolling Ops v1 — coordinated rolling operations for Juju charms.

This library provides a reusable mechanism for coordinating rolling operations
across units of a Juju application using a peer-relation distributed lock.

The library guarantees that at most one unit executes a rolling operation at any
time, while allowing multiple units to enqueue operations and participate
in a coordinated rollout.

## Data model (peer relation)

### Unit databag

Each unit maintains a FIFO queue of operations it wishes to execute.

Keys:
- `operations`: JSON-encoded list of queued `Operation` objects
- `state`: `"idle"` | `"request"` | `"retry-release"` | `"retry-hold"`
- `executed_at`: UTC timestamp string indicating when the current operation last ran

Each `Operation` contains:
- `callback_id`: identifier of the callback to execute
- `kwargs`: JSON-serializable arguments for the callback
- `requested_at`: UTC timestamp when the operation was enqueued
- `max_retry (optional)`: maximum retry count. `None` means unlimited
- `attempt`: current attempt number

### Application databag

The application databag represents the global lock state.

Keys:
- `granted_unit`: unit identifier (unit name), or empty
- `granted_at`: UTC timestamp indicating when the lock was granted

## Operation semantics

- Units enqueue operations instead of overwriting a single pending request.
- Duplicate operations (same `callback_id` and `kwargs`) are ignored if they are
  already the last queued operation.
- When granted the lock, a unit executes exactly one operation (the queue head).
- After execution, the lock is released so that other units may proceed.

## Retry semantics

- If a callback returns `OperationResult.RETRY_RELEASE` the unit will release the
lock and retry the operation later.
- If a callback returns `OperationResult.RETRY_HOLD` the unit will keep the
lock and retry immediately.
- Retry state (`attempt`) is tracked per operation.
- When `max_retry` is exceeded, the failing operation is dropped and the unit
  proceeds to the next queued operation, if any.

## Scheduling semantics

- Only the leader schedules lock grants.
- If a valid lock grant exists, no new unit is scheduled.
- Requests are preferred over retries.
- Among requests, the operation with the oldest `requested_at` timestamp is selected.
- Among retries, the operation with the oldest `executed_at` timestamp is selected.
- Stale grants (e.g., pointing to departed units) are automatically released.

All timestamps are stored in UTC using ISO 8601 format.

## Using the library in a charm

### 1. Declare a peer relation

```yaml
peers:
  restart:
    interface: rolling_op
```

Import this library into src/charm.py, and initialize a PeerRollingOpsManager in the Charm's
`__init__`. The Charm should also define a callback routine, which will be executed when
a unit holds the distributed lock:

src/charm.py
```python
from charms.rolling_ops.v1.rollingops import PeerRollingOpsManager, OperationResult

class SomeCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.rolling_ops = PeerRollingOpsManager(
            charm=self,
            relation_name="restart",
            callback_targets={
                "restart": self._restart,
                "failed_restart": self._failed_restart,
                "defer_restart": self._defer_restart,
            },
        )

    def _restart(self, force: bool) -> OperationResult:
        # perform restart logic
        return OperationResult.RELEASE

    def _failed_restart(self) -> OperationResult:
        # perform restart logic
        return OperationResult.RETRY_RELEASE

    def _defer_restart(self) -> OperationResult:
        if not self.some_condition():
            return OperationResult.RETRY_HOLD
        # do restart logic
        return OperationResult.RELEASE
```

Request a rolling operation

```python

    def _on_restart_action(self, event) -> None:
        self.rolling_ops.request_async_lock(
            callback_id="restart",
            kwargs={"force": True},
            max_retry=3,
    )
```

All participating units must enqueue the operation in order to be included
in the rolling execution.

Units that do not enqueue the operation will be skipped, allowing operators
to recover from partial failures by reissuing requests selectively.

Do not include sensitive information in the kwargs of the callback.
These values will be stored in the databag.

Make sure that callback_targets is not dynamic and that the mapping
contains the expected values at the moment of the callback execution.
"""

import logging
from collections.abc import Callable
from typing import Any

from ops import Relation
from ops.charm import (
    CharmBase,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import EventBase, Object

from charmlibs.rollingops._peer_models import (
    Lock,
    LockIterator,
    OperationResult,
    RollingOpsDecodingError,
    RollingOpsInvalidLockRequestError,
    RollingOpsNoRelationError,
    pick_oldest_completed,
    pick_oldest_request,
)
from charmlibs.rollingops._peer_worker import PeerRollingOpsAsyncWorker

logger = logging.getLogger(__name__)



class PeerRollingOpsManager(Object):
    """Emitters and handlers for rolling ops."""

    def __init__(
        self, charm: CharmBase, relation_name: str, callback_targets: dict[str, Callable[..., Any]]
    ):
        """Register our custom events.

        params:
            charm: the charm we are attaching this to.
            relation_name: the peer relation name from metadata.yaml.
            callback_targets: mapping from callback_id -> callable.
        """
        super().__init__(charm, 'peer-rolling-ops-manager')
        self._charm = charm
        self.relation_name = relation_name
        self.callback_targets = callback_targets
        self.charm_dir = charm.charm_dir
        self.worker = PeerRollingOpsAsyncWorker(charm, relation_name=relation_name)

        self.framework.observe(
            charm.on[self.relation_name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            charm.on[self.relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(charm.on.leader_elected, self._process_locks)
        self.framework.observe(charm.on.rollingops_lock_granted, self._on_rollingops_lock_granted)
        self.framework.observe(charm.on.update_status, self._on_rollingops_lock_granted)

    @property
    def _relation(self) -> Relation | None:
        """Returns the peer relation used to manage locks."""
        return self.model.get_relation(self.relation_name)

    def _on_rollingops_lock_granted(self, event) -> None:
        """Handler of the custom hook rollingops_lock_granted.

        The custom hook is triggered by a background process.
        """
        if not self._relation:
            return
        logger.info('Received a rolling-ops lock granted event.')
        lock = Lock(self.model, self.relation_name, self.model.unit)
        if lock.should_run():
            self._on_run_with_lock()
            self._process_locks()

    def _on_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Leader cleanup: if a departing unit was granted a lock, clear the grant.

        This prevents deadlocks when the granted unit leaves the relation.
        """
        if not self.model.unit.is_leader():
            return
        if unit := event.departing_unit:
            lock = Lock(self.model, self.relation_name, unit)
            if lock.is_granted():
                lock.release()
                self._process_locks()

    def _on_relation_changed(self, _: RelationChangedEvent) -> None:
        """Process relation changed."""
        if self.model.unit.is_leader():
            self._process_locks()
            return

        lock = Lock(self.model, self.relation_name, self.model.unit)
        if lock.should_run():
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

        if not (granted_unit := self._relation.data[self.model.app].get('granted_unit', '')):
            return

        valid_units = self._valid_peer_unit_names()
        if granted_unit not in valid_units:
            logger.warning(
                'granted_unit=%s is not in current peer units; releasing stale grant.',
                granted_unit,
            )
            self._relation.data[self.model.app].update({'granted_unit': '', 'granted_at': ''})

    def _process_locks(self, _: EventBase | None = None) -> None:
        """Process locks.

        This method is only executed by the leader unit.
        It effectively releases the lock and triggers scheduling.
        """
        if not self.model.unit.is_leader():
            return

        for lock in LockIterator(self.model, self.relation_name):
            if lock.should_release():
                lock.release()
                break

        self._release_stale_grant()
        granted_unit = self._relation.data[self.model.app].get('granted_unit', '')  # type: ignore[reportOptionalMemberAccess]

        if granted_unit:
            logger.info('Current granted_unit=%s. No new unit will be scheduled.', granted_unit)
            return

        self._schedule()

    def _schedule(self) -> None:
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

        pending_requests: list[Lock] = []
        pending_retries: list[Lock] = []

        for lock in LockIterator(self.model, self.relation_name):
            if lock.is_retry_hold():
                self._grant_lock(lock)
                return
            if lock.is_waiting():
                pending_requests.append(lock)
            elif lock.is_waiting_retry():
                pending_retries.append(lock)

        selected = None
        if pending_requests:
            selected = pick_oldest_request(pending_requests)
        elif pending_retries:
            selected = pick_oldest_completed(pending_retries)

        if not selected:
            logger.info('No pending lock requests. Lock was not granted to any unit.')
            return

        self._grant_lock(selected)

    def _grant_lock(self, selected: Lock) -> None:
        """Grant the lock to the selected unit.

        If the lock is granted to the leader unit:
            - If it is a retry, starts the worker to break the loop before next execution.
            - Otherwise, the callback is run immediately

        Args:
            selected: The lock instance to grant.
        """
        selected.grant()
        logger.info('Lock granted to unit=%s.', selected.unit.name)
        if selected.unit == self.model.unit:
            if selected.is_retry():
                self.worker.start()
                return
            self._on_run_with_lock()
            self._process_locks()

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
            lock = Lock(self.model, self.relation_name, self.model.unit)
            lock.request(callback_id, kwargs, max_retry)

        except (RollingOpsDecodingError, ValueError) as e:
            logger.error('Failed operation: %s', e)
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
        lock = Lock(self.model, self.relation_name, self.model.unit)

        if not lock.is_granted():
            logger.debug('Lock is not granted. Operation will not run.')
            return

        if not (operation := lock.get_current_operation()):
            logger.debug('There is no operation to run.')
            lock.complete()
            return

        if not (callback := self.callback_targets.get(operation.callback_id)):
            logger.warning(
                'Operation %s target was not found. It cannot be executed.',
                operation.callback_id,
            )
            return
        logger.info(
            'Executing callback_id=%s, attempt=%s', operation.callback_id, operation.attempt
        )
        try:
            result = callback(**operation.kwargs)
        except Exception as e:
            logger.exception('Operation failed: %s: %s', operation.callback_id, e)
            result = OperationResult.RETRY_RELEASE

        match result:
            case OperationResult.RETRY_HOLD:
                logger.info(
                    'Finished %s. Operation will be retried immediately.', operation.callback_id
                )
                lock.retry_hold()

            case OperationResult.RETRY_RELEASE:
                logger.info('Finished %s. Operation will be retried later.', operation.callback_id)
                lock.retry_release()

            case _:
                logger.info('Finished %s. Lock will be released.', operation.callback_id)
                lock.complete()
