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

"""Common rolling-ops interface coordinating etcd-backed and peer-backed execution."""

import logging
from contextlib import contextmanager
from typing import Any

from ops import CharmBase, Object, Relation, RelationBrokenEvent
from ops.framework import EventBase
from pydantic import ValidationError

from charmlibs.rollingops.common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsInvalidLockRequestError,
    RollingOpsNoRelationError,
    RollingOpsSyncLockError,
)
from charmlibs.rollingops.common._models import (
    Operation,
    OperationQueue,
    ProcessingBackend,
    RollingOpsState,
    RollingOpsStatus,
    RunWithLockStatus,
    SyncLockBackend,
    UnitBackendState,
)
from charmlibs.rollingops.common._utils import ETCD_FAILED_HOOK_NAME, LOCK_GRANTED_HOOK_NAME
from charmlibs.rollingops.etcd._backend import EtcdRollingOpsBackend
from charmlibs.rollingops.peer._backend import PeerRollingOpsBackend
from charmlibs.rollingops.peer._models import PeerUnitOperations

logger = logging.getLogger(__name__)


class RollingOpsLockGrantedEvent(EventBase):
    """Custom event emitted when the background worker grants the lock."""


class RollingOpsEtcdFailedEvent(EventBase):
    """Custom event emitted when the etcd worker hits a fatal error."""


class RollingOpsManager(Object):
    """Coordinate rolling operations across etcd and peer backends.

    This object exposes a common API for queuing asynchronous rolling
    operations and acquiring synchronous locks. It prefers etcd when
    available, mirrors operation state into the peer relation, and falls
    back to peer-based processing when etcd becomes unavailable or
    inconsistent.
    """

    def __init__(
        self,
        charm: CharmBase,
        callback_targets: dict[str, Any],
        peer_relation_name: str,
        etcd_relation_name: str | None = None,
        cluster_id: str | None = None,
        sync_lock_targets: dict[str, type[SyncLockBackend]] | None = None,
        base_dir: str = '/var/lib/rollingops',
    ):
        """Create a rolling operations manager with etcd and peer backends.

        This manager coordinates rolling operations across two backends:

        - an etcd-backed backend, used when etcd is available
        - a peer-relation-backed backend, used as a fallback

        Operations are always persisted in the peer backend. When etcd is
        available, operations are also mirrored to etcd and processed there.
        If etcd becomes unavailable or unhealthy, this manager falls back to
        the peer backend and continues processing from the mirrored state.

        Args:
            charm: The charm instance owning this manager.
            callback_targets: Mapping of callback identifiers to callables
                executed when queued operations are granted the lock.
            peer_relation_name: Name of the peer relation used for fallback
                state and operation mirroring.
            etcd_relation_name: Name of the relation providing etcd access.
                If not provided, only peer backend is used.
            cluster_id: Identifier used to scope etcd-backed state for this
                rolling-ops instance.
            sync_lock_targets: Optional mapping of sync lock backend
                identifiers to backend implementations used when acquiring
                synchronous locks through the peer fallback path.
            base_dir: base directory where all files related to rollingops will be written.
        """
        super().__init__(charm, 'rolling-ops-manager')

        self.charm = charm
        self.peer_relation_name = peer_relation_name
        self.etcd_relation_name = etcd_relation_name
        self._sync_lock_targets = sync_lock_targets or {}
        charm.on.define_event(LOCK_GRANTED_HOOK_NAME, RollingOpsLockGrantedEvent)
        charm.on.define_event(ETCD_FAILED_HOOK_NAME, RollingOpsEtcdFailedEvent)

        self.peer_backend = PeerRollingOpsBackend(
            charm=charm,
            relation_name=peer_relation_name,
            callback_targets=callback_targets,
            base_dir=base_dir,
        )
        self.etcd_backend: EtcdRollingOpsBackend | None = None
        if etcd_relation_name and cluster_id:
            self.etcd_backend = EtcdRollingOpsBackend(
                charm=charm,
                peer_relation_name=peer_relation_name,
                etcd_relation_name=etcd_relation_name,
                cluster_id=cluster_id,
                callback_targets=callback_targets,
                base_dir=base_dir,
            )
            self.framework.observe(
                charm.on[etcd_relation_name].relation_broken,
                self._on_etcd_relation_broken,
            )

        self.framework.observe(charm.on.rollingops_lock_granted, self._on_rollingops_lock_granted)
        self.framework.observe(charm.on.rollingops_etcd_failed, self._on_rollingops_etcd_failed)
        self.framework.observe(charm.on.update_status, self._on_update_status)

    @property
    def _peer_relation(self) -> Relation | None:
        """Return the peer relation for this charm."""
        return self.model.get_relation(self.peer_relation_name)

    @property
    def _backend_state(self) -> UnitBackendState:
        """Return the backend selection state stored for the current unit.

        This state determines whether the current unit is managed by the etcd
        backend or the peer backend, and is used to control fallback and
        recovery decisions.
        """
        return UnitBackendState(self.model, self.peer_relation_name, self.model.unit)

    def _on_etcd_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the etcd relation being fully removed.

        This method stops the etcd worker process since the required
        relation is no longer available.
        """
        self._fallback_current_unit_to_peer()

    def _select_processing_backend(self) -> ProcessingBackend:
        """Choose which backend should handle new operations for this unit.

        Etcd is preferred when available, but a unit that has fallen back to
        peer remains peer-managed until its pending peer work is drained.
        This ensures backend transitions happen only from a clean state.

        Returns:
            The selected processing backend.
        """
        if self.etcd_backend is None:
            logger.info('etcd backend not configured; selecting peer backend.')
            return ProcessingBackend.PEER

        if not self.etcd_backend.is_available():
            logger.info('etcd backend unavailable; selecting peer backend.')
            return ProcessingBackend.PEER

        if self._backend_state.is_peer_managed() and not self.peer_backend.has_pending_work():
            logger.info('etcd backend is available. Switching to etcd backend.')
            return ProcessingBackend.ETCD

        if self._backend_state.is_etcd_managed():
            logger.info('etcd backend selected.')
            return ProcessingBackend.ETCD

        logger.info('peer backend selected.')
        return ProcessingBackend.PEER

    def _fallback_current_unit_to_peer(self) -> None:
        """Move the current unit to the peer backend and resume processing there.

        This method marks the unit as peer-managed, stops the etcd worker,
        and ensures that peer-based processing is running.

        It is used when etcd becomes unavailable, unhealthy, or inconsistent,
        so that queued operations can continue without being lost.
        """
        self._backend_state.fallback_to_peer()
        if self.etcd_backend is not None:
            self.etcd_backend.worker.stop()
        self.peer_backend.ensure_processing()

    def request_async_lock(
        self,
        callback_id: str,
        kwargs: dict[str, Any] | None = None,
        max_retry: int | None = None,
    ) -> None:
        """Queue a rolling operation and trigger processing on the active backend.

        A new operation is created and always persisted in the peer backend.
        If etcd is currently selected as the processing backend, the operation
        is also mirrored to etcd and processing is triggered there.

        If persisting to etcd fails, the manager falls back to peer-based
        processing. This guarantees that operations remain schedulable even
        when etcd is unavailable.

        Args:
            callback_id: Identifier of the callback to execute when the
                operation is granted the rolling lock.
            kwargs: Optional keyword arguments passed to the callback target.
            max_retry: Optional maximum number of retries allowed for the
                operation. None means infinte retries.

        Raises:
            RollingOpsInvalidLockRequestError: If the callback identifier is
                unknown, the operation cannot be created, or it cannot be
                persisted in the peer backend.
            RollingOpsNoRelationError: If the peer relation is not available.
        """
        if callback_id not in self.peer_backend.callback_targets:
            raise RollingOpsInvalidLockRequestError(f'Unknown callback_id: {callback_id}')

        if not self._peer_relation:
            raise RollingOpsNoRelationError('No %s peer relation yet.', self.peer_relation_name)

        if kwargs is None:
            kwargs = {}

        backend = self._select_processing_backend()

        try:
            operation = Operation.create(callback_id, kwargs, max_retry)
        except (RollingOpsDecodingError, ValueError) as e:
            logger.error('Failed to create operation: %s', e)
            raise RollingOpsInvalidLockRequestError('Failed to create the lock request') from e

        try:
            self.peer_backend.enqueue_operation(operation)
        except (RollingOpsDecodingError, ValueError) as e:
            logger.error('Failed to persists operation in peer backend: %s', e)
            raise RollingOpsInvalidLockRequestError(
                'Failed to persists operation in peer backend.'
            ) from e

        if backend == ProcessingBackend.ETCD and self.etcd_backend is not None:
            try:
                self.etcd_backend.enqueue_operation(operation)
            except Exception as e:
                logger.warning(
                    'Failed to persist operation in etcd backend; falling back to peer: %s',
                    e,
                )
                backend = ProcessingBackend.PEER

        if backend == ProcessingBackend.ETCD and self.etcd_backend is not None:
            self.etcd_backend.ensure_processing()
        else:
            self._fallback_current_unit_to_peer()

    def _on_rollingops_lock_granted(self, event: RollingOpsLockGrantedEvent) -> None:
        """Handle a granted rolling lock and dispatch execution to the active backend.

        If the current unit is peer-managed, the operation is executed through
        the peer backend.

        If the current unit is etcd-managed, the operation is executed through
        the etcd backend.
        """
        if self._backend_state.is_peer_managed():
            logger.info('Executing rollingop on peer backend.')
            self.peer_backend._on_rollingops_lock_granted(event)
            return
        self._run_etcd_and_mirror_or_fallback()

    def _run_etcd_and_mirror_or_fallback(self) -> None:
        """Run the etcd execution path and mirror its outcome to peer.

        On successful execution, the result is mirrored back
        to the peer relation so that peer state remains consistent and can be
        used for fallback.

        If etcd execution fails or mirrored state becomes inconsistent, the
        manager falls back to the peer backend and resumes processing there.
        """
        if self.etcd_backend is None:
            logger.info('etcd backend not configured; using peer backend.')
            self._fallback_current_unit_to_peer()
            return

        try:
            logger.info('Executing rollingop on etcd backend.')
            outcome = self.etcd_backend._on_run_with_lock()
        except Exception as e:
            logger.warning(
                'etcd backend failed while handling rollingops_lock_granted; '
                'falling back to peer: %s',
                e,
            )
            self._fallback_current_unit_to_peer()
            return

        try:
            self.peer_backend.mirror_outcome(outcome)
        except RollingOpsDecodingError:
            logger.info(
                'Inconsistencies found between peer relation and etcd. '
                'Falling back to peer backend.'
            )
            self._fallback_current_unit_to_peer()
            return
        logger.info('Execution mirrored to peer relation.')
        if outcome.status == RunWithLockStatus.EXECUTED_NOT_COMMITTED:
            self._fallback_current_unit_to_peer()
            logger.info('Fell back to peer backend.')

    def _on_rollingops_etcd_failed(self, event: RollingOpsEtcdFailedEvent) -> None:
        """Fall back to peer when the etcd worker reports a fatal failure."""
        logger.warning('Received %s.', ETCD_FAILED_HOOK_NAME)
        if self._backend_state.is_etcd_managed():
            # No need to stop the background process. This hook means that it stopped.
            self._backend_state.fallback_to_peer()
            self.peer_backend.ensure_processing()
            logger.info('Fell back to peer backend.')

    def _get_sync_lock_backend(self, backend_id: str) -> SyncLockBackend:
        """Instantiate the configured peer sync lock backend.

        Args:
            backend_id: Identifier of the configured sync lock backend.

        Returns:
            A new sync lock backend instance.

        Raises:
            RollingOpsSyncLockError: If no backend is registered for
                the given identifier.
        """
        backend_cls = self._sync_lock_targets.get(backend_id, None)
        if backend_cls is None:
            raise RollingOpsSyncLockError(f'Unknown sync lock backend: {backend_id}.')

        return backend_cls()

    @contextmanager
    def acquire_sync_lock(self, backend_id: str, timeout: int):
        """Acquire a synchronous lock, using etcd when available and peer as fallback.

        This context manager first attempts to acquire the lock through the
        etcd backend. If etcd is available and the lock is acquired, the
        protected block is executed under the etcd lock.

        If etcd fails due to an operational error, the manager falls back to
        the configured peer sync lock backend identified by `backend_id`.
        If etcd acquisition times out, the timeout is propagated and no
        fallback occurs.

        On context exit, the acquired lock is released through the backend
        that granted it.

        Args:
            backend_id: Identifier of the peer sync lock backend to use if
                etcd acquisition cannot be used.
            timeout: Maximum time in seconds to wait for lock acquisition.
                None means infinite time.

        Yields:
            None. The protected code runs while the lock is held.

        Raises:
            TimeoutError: If lock acquisition through etcd or the peer backend
                times out.
            RollingOpsSyncLockError: if there is an error when acquiring the lock.
        """
        if self.etcd_backend is not None and self.etcd_backend.is_available():
            logger.info('Acquiring sync lock on etcd.')
            try:
                self.etcd_backend.acquire_sync_lock(timeout)
                yield
                return
            except TimeoutError:
                raise
            except Exception as e:
                # etcd is not reachable or unhealthy
                logger.exception(
                    'Failed to request etcd sync lock; falling back to peer: %s',
                    e,
                )
            finally:
                try:
                    self.etcd_backend.release_sync_lock()
                    logger.info('etcd lock released.')
                except Exception as e:
                    logger.exception('Failed to release sync lock: %s', e)

        backend = self._get_sync_lock_backend(backend_id)
        logger.info('Acquiring sync lock backend %s.', backend_id)
        try:
            backend.acquire(timeout=timeout)
        except Exception as e:
            raise RollingOpsSyncLockError(
                f'Failed to acquire sync lock backend {backend_id}'
            ) from e

        try:
            yield
        finally:
            try:
                backend.release()
                logger.info('Sync lock backend %s released.', backend_id)
            except Exception as e:
                raise RollingOpsSyncLockError(
                    f'Failed to release sync lock backend {backend_id}'
                ) from e

    @property
    def state(self) -> RollingOpsState:
        """Return the current rolling-ops state for this unit.

        The returned state is always based on the peer relation for the
        operation queue, since peer state is the durable fallback source of
        truth.

        Status is taken from the etcd backend when this unit is currently
        etcd-managed. If status retrieval from etcd fails, the unit falls
        back to the peer backend and peer status is returned instead.

        Returns:
            A snapshot of the current rolling-ops status, backend selection,
            and queued operations for this unit.
        """
        if self._peer_relation is None:
            return RollingOpsState(
                status=RollingOpsStatus.UNAVAILABLE,
                processing_backend=ProcessingBackend.PEER,
                operations=OperationQueue(),
            )

        status = self.peer_backend.get_status()
        if self.etcd_backend is not None and self._backend_state.is_etcd_managed():
            status = self.etcd_backend.get_status()
            if status == RollingOpsStatus.UNAVAILABLE:
                logger.info('etcd backend is not available. Falling back to peer backend.')
                self._fallback_current_unit_to_peer()
                status = self.peer_backend.get_status()

        operations = PeerUnitOperations(self.model, self.peer_relation_name, self.model.unit)
        return RollingOpsState(
            status=status,
            processing_backend=self._backend_state.backend,
            operations=operations.queue,
        )

    def is_waiting(self, callback_id: str, kwargs: dict[str, Any] | None = None) -> bool:
        """Return whether the current unit has a pending operation matching callback and kwargs."""
        if self._peer_relation is None:
            return False

        operations = PeerUnitOperations(
            self.model,
            self.peer_relation_name,
            self.model.unit,
        ).queue.operations

        kwargs = kwargs or {}

        try:
            check_operation = Operation.create(callback_id=callback_id, kwargs=kwargs)
        except ValidationError:
            return False

        return any(op == check_operation for op in operations)

    def _on_update_status(self, event: EventBase) -> None:
        """Periodic reconciliation of rolling-ops state."""
        logger.info('Received a update-status event.')
        if self._backend_state.is_etcd_managed():
            if self.etcd_backend is None or not self.etcd_backend.is_available():
                logger.warning('etcd unavailable during update_status; falling back.')
                self._fallback_current_unit_to_peer()
                return

            if not self.etcd_backend.is_processing():
                logger.warning(
                    'etcd backend is selected but no worker process is running; falling back.'
                )
                self._fallback_current_unit_to_peer()
                return

            self._run_etcd_and_mirror_or_fallback()
            return

        self.peer_backend._on_rollingops_lock_granted(event)
