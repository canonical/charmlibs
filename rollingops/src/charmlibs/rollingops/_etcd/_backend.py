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
import time
from typing import Any

from ops import Object, Relation
from ops.charm import (
    CharmBase,
    RelationCreatedEvent,
    RelationDepartedEvent,
)

from charmlibs import pathops
from charmlibs.rollingops._common._exceptions import (
    RollingOpsInvalidLockRequestError,
    RollingOpsNoEtcdRelationError,
    RollingOpsSyncLockError,
)
from charmlibs.rollingops._common._models import (
    OperationResult,
    RollingOpsStatus,
    _Operation,
    _RunWithLockOutcome,
    _RunWithLockStatus,
    _UnitBackendState,
)
from charmlibs.rollingops._etcd._etcd import EtcdLease, EtcdLock, ManagerOperationStore
from charmlibs.rollingops._etcd._etcdctl import ETCDCTL_CMD, Etcdctl
from charmlibs.rollingops._etcd._models import RollingOpsKeys
from charmlibs.rollingops._etcd._relations import EtcdRequiresV1, SharedClientCertificateManager
from charmlibs.rollingops._etcd._worker import EtcdRollingOpsAsyncWorker

logger = logging.getLogger(__name__)


class _EtcdRollingOpsBackend(Object):  # pyright: ignore[reportUnusedClass]
    """Manage rolling operations using etcd-backed coordination.

    This backend stores operation state in etcd, coordinates asynchronous
    execution through an etcd-backed distributed lock, and exposes a
    synchronous lock interface for critical sections.

    Each unit manages its own etcd worker process and operation queues.
    Operations are scoped using a cluster identifier and a per-unit owner.
    """

    def __init__(
        self,
        charm: CharmBase,
        peer_relation_name: str,
        etcd_relation_name: str,
        cluster_id: str,
        callback_targets: dict[str, Any],
        base_dir: pathops.LocalPath,
    ):
        """Initialize the etcd-backed rolling-ops backend.

        Args:
            charm: The charm instance owning this backend.
            peer_relation_name: Name of the peer relation used for shared
                state and worker coordination.
            etcd_relation_name: Name of the relation providing etcd access.
            cluster_id: Identifier used to scope etcd keys for this rolling-ops
                instance.
            callback_targets: Mapping from callback identifiers to callables
                executed when an operation is granted the asynchronous lock.
            base_dir: base directory where all files related to rollingops will be written.
        """
        super().__init__(charm, 'etcd-rolling-ops-manager')
        self._charm = charm
        self.peer_relation_name = peer_relation_name
        self.etcd_relation_name = etcd_relation_name
        self.callback_targets = callback_targets
        self._base_dir = base_dir

        self.etcdctl = Etcdctl(self._base_dir)

        owner = f'{self.model.uuid}-{self.model.unit.name}'.replace('/', '-')
        self.worker = EtcdRollingOpsAsyncWorker(
            charm,
            peer_relation_name=peer_relation_name,
            owner=owner,
            cluster_id=cluster_id,
            base_dir=self._base_dir,
        )
        self.keys = RollingOpsKeys.for_owner(cluster_id=cluster_id, owner=owner)

        self.shared_certificates = SharedClientCertificateManager(
            charm,
            peer_relation_name=peer_relation_name,
            base_dir=self._base_dir,
        )

        self.etcd = EtcdRequiresV1(
            charm,
            relation_name=etcd_relation_name,
            cluster_id=self.keys.cluster_prefix,
            shared_certificates=self.shared_certificates,
            base_dir=self._base_dir,
        )
        self._async_lock = EtcdLock(
            lock_key=self.keys.lock_key, owner=owner, base_dir=self._base_dir
        )
        self._sync_lock = EtcdLock(
            lock_key=self.keys.lock_key, owner=f'{owner}:sync', base_dir=self._base_dir
        )
        self._lease: EtcdLease | None = None
        self.operations_store = ManagerOperationStore(self.keys, owner, base_dir=self._base_dir)

        self.framework.observe(
            charm.on[self.peer_relation_name].relation_departed, self._on_peer_relation_departed
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_created, self._on_etcd_relation_created
        )

    @property
    def _peer_relation(self) -> Relation | None:
        """Return the peer relation for this backend."""
        return self.model.get_relation(self.peer_relation_name)

    @property
    def _etcd_relation(self) -> Relation | None:
        """Return the etcd relation for this backend."""
        return self.model.get_relation(self.etcd_relation_name)

    def is_available(self) -> bool:
        """Return whether the etcd backend is currently usable.

        The backend is considered available only if the etcd relation exists
        and the etcd client has been initialized successfully.

        Returns:
            True if etcd can currently be used, otherwise False.
        """
        if self._etcd_relation is None:
            return False
        try:
            self.etcdctl.ensure_initialized()
        except Exception:
            return False
        return True

    def enqueue_operation(self, operation: _Operation) -> None:
        """Persist an operation in etcd for this unit.

        Before storing the operation, this method clears any pending fallback
        state for the current unit. If the unit had previously fallen back
        from etcd to peer processing and cleanup is still required, stale etcd
        operation state is removed first so processing can resume from a clean
        slate.

        Args:
            operation: The operation to enqueue.

        Raises:
            RollingOpsNoEtcdRelationError: If the etcd relation does not exist.
            RollingOpsEtcdNotConfiguredError: If the etcd client has not been
                configured yet.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        if self._etcd_relation is None:
            raise RollingOpsNoEtcdRelationError

        self.etcdctl.ensure_initialized()

        backend_state = _UnitBackendState(self.model, self.peer_relation_name, self.model.unit)
        if backend_state.cleanup_needed:
            self.operations_store.clean_up()
        backend_state.clear_fallback()

        self.operations_store.request(operation)

    def ensure_processing(self):
        """Ensure that the etcd worker process is running.

        The worker is responsible for acquiring the asynchronous lock and
        processing queued operations for this unit.
        """
        self.worker.start()

    def is_processing(self) -> bool:
        """Return whether the etcd worker process is currently running."""
        return self.worker.is_running()

    def _on_etcd_relation_created(self, event: RelationCreatedEvent) -> None:
        """Validate that the etcdctl command is available when etcd is related.

        Args:
            event: The relation-created event for the etcd relation.
        """
        if not self.etcdctl.is_etcdctl_installed():
            logger.error('%s is not installed.', ETCDCTL_CMD)

    def _on_peer_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Handle removal of a unit from the peer relation.

        If the current unit is departing, the etcd worker process is stopped
        to ensure a clean shutdown and avoid leaving a stale worker running.

        Args:
            event: The peer relation departed event.
        """
        unit = event.departing_unit
        if unit == self.model.unit:
            self.worker.stop()

    def request_async_lock(
        self,
        callback_id: str,
        kwargs: dict[str, Any] | None = None,
        max_retry: int | None = None,
    ) -> None:
        """Queue a rolling operation and trigger asynchronous lock acquisition.

        This method creates a new operation representing a callback to execute
        once the distributed lock is granted. The operation is appended to the
        unit's pending operation queue stored in etcd.

        If the operation is successfully enqueued, the background worker process
        responsible for acquiring the distributed lock and processing operations
        is started.

        Args:
            callback_id: Identifier of the registered callback to execute when
                the lock is granted.
            kwargs: Optional keyword arguments passed to the callback when
                executed. Must be JSON-serializable.
            max_retry: Maximum number of retries for the operation.
                - None: retry indefinitely
                - 0: do not retry on failure

        Raises:
            RollingOpsInvalidLockRequestError: If the callback_id is not registered or
                invalid parameters were provided.
            RollingOpsNoEtcdRelationError: if the etcd relation does not exist
            RollingOpsEtcdNotConfiguredError: if etcd client has not been configured yet
            PebbleConnectionError: if the remote container cannot be reached.
        """
        if callback_id not in self.callback_targets:
            raise RollingOpsInvalidLockRequestError(f'Unknown callback_id: {callback_id}')

        if not self._etcd_relation:
            raise RollingOpsNoEtcdRelationError

        self.etcdctl.ensure_initialized()

        if kwargs is None:
            kwargs = {}

        operation = _Operation.create(callback_id, kwargs, max_retry)
        self.operations_store.request(operation)
        self.worker.start()

    def _on_run_with_lock(self) -> _RunWithLockOutcome:
        """Execute the current operation while holding the distributed lock.

        This method is triggered when the worker determines that the current
        unit owns the distributed lock. The method retrieves the head operation
        from the in-progress queue and executes its registered callback.

        After execution, the operation is moved to the completed queue and its
        updated state is persisted.

        Returns:
            A structured outcome describing whether an operation was executed
            and, if so, which operation was finalized and with what result.

        Raises:
            RollingOpsEtcdTransactionError: if the operation cannot be marked
                as completed.
        """
        if not self._async_lock.is_held():
            logger.info('Lock is not granted. Operation will not run.')
            return _RunWithLockOutcome(status=_RunWithLockStatus.NOT_GRANTED)

        if not (operation := self.operations_store.peek_current()):
            logger.info('Lock granted but there is no operation to run.')
            return _RunWithLockOutcome(status=_RunWithLockStatus.NO_OPERATION)

        if not (callback := self.callback_targets.get(operation.callback_id)):
            logger.error(
                'Operation %s target was not found. Releasing operation without retry.',
                operation.callback_id,
            )
            self.operations_store.finalize(operation, OperationResult.RELEASE)
            return _RunWithLockOutcome(
                status=_RunWithLockStatus.MISSING_CALLBACK,
                op_id=operation.op_id,
                result=OperationResult.RELEASE,
            )
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
            case OperationResult.RETRY_RELEASE:
                logger.info('Finished %s. Operation will be retried later.', operation.callback_id)
            case _:
                logger.info('Finished %s. Lock will be released.', operation.callback_id)
                result = OperationResult.RELEASE

        try:
            self.operations_store.finalize(operation, result)
        except Exception:
            logger.exception('Failed to commit operation %s to etcd.', operation.callback_id)
            return _RunWithLockOutcome(
                status=_RunWithLockStatus.EXECUTED_NOT_COMMITTED,
                op_id=operation.op_id,
                result=result,
            )
        return _RunWithLockOutcome(
            status=_RunWithLockStatus.EXECUTED,
            op_id=operation.op_id,
            result=result,
        )

    def acquire_sync_lock(self, timeout: int | None) -> None:
        """Acquire the etcd-backed synchronous lock for this unit.

        A dedicated lease is granted and kept alive for the duration of the
        lock. The backend then repeatedly attempts to acquire the sync lock
        until it succeeds or the timeout expires.

        Args:
            timeout: Maximum time in seconds to wait for the lock.
                None means wait indefinitely.

        Raises:
            TimeoutError: If the lock could not be acquired before the timeout.
            RollingOpsSyncLockError: if there was an error obtaining the lock.
        """
        self._lease = EtcdLease(self._base_dir)

        deadline = None if timeout is None else time.monotonic() + timeout

        try:
            self._lease.grant()

            if self._lease.id is None:
                raise RollingOpsSyncLockError('Failed to grant an etcd lease.')
            while True:
                try:
                    if self._sync_lock.try_acquire(self._lease.id):
                        logger.info('etcd lock acquired.')
                        return
                except Exception:
                    logger.exception('Failed while trying to acquire etcd sync lock.')
                    raise

                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError(f'Timed out acquiring etcd sync lock after {timeout}s.')

                time.sleep(15)

        except Exception as e:
            try:
                self._lease.revoke()
            except Exception:
                logger.exception('Failed to revoke lease %s.', self._lease.id)
            raise RollingOpsSyncLockError('Failed to acquire the etcd sync lock') from e

    def release_sync_lock(self) -> None:
        """Release the synchronous lock and revoke its lease."""
        self._sync_lock.release()
        if self._lease is not None:
            self._lease.revoke()

    def get_status(self) -> RollingOpsStatus:
        """Return the rolling-ops status for this unit in etcd mode.

        Status is derived from the current etcd-backed lock state and the
        unit's queued operation state.

        Returned values:
            - NOT_READY: etcd backend is not available
            - GRANTED: the async lock is currently held by this unit
            - WAITING: this unit has queued work but does not hold the lock
            - IDLE: this unit has no pending work

        Returns:
            The current rolling-ops status for this unit.
        """
        if self._peer_relation is None or self._etcd_relation is None or not self.is_available():
            return RollingOpsStatus.NOT_READY

        if self._async_lock.is_held():
            return RollingOpsStatus.GRANTED

        if self.operations_store.has_pending_work():
            return RollingOpsStatus.WAITING

        return RollingOpsStatus.IDLE
