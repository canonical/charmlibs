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

"""Rollingops common API interface."""

import logging
from contextlib import contextmanager
from typing import Any

from ops import CharmBase, Object, Relation, RelationBrokenEvent
from ops.framework import EventBase

from charmlibs.pathops import PebbleConnectionError
from charmlibs.rollingops.common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsEtcdctlError,
    RollingOpsEtcdNotConfiguredError,
    RollingOpsFileSystemError,
    RollingOpsInvalidLockRequestError,
    RollingOpsNoEtcdRelationError,
    RollingOpsNoRelationError,
    RollingOpsSyncLockBackendError,
)
from charmlibs.rollingops.common._models import (
    Operation,
    OperationQueue,
    ProcessingBackend,
    RollingOpsState,
    RollingOpsStatus,
    SyncLockBackend,
    UnitBackendState,
)
from charmlibs.rollingops.etcd._manager import EtcdRollingOpsManager
from charmlibs.rollingops.peer._manager import PeerRollingOpsManager
from charmlibs.rollingops.peer._models import PeerUnitOperations

logger = logging.getLogger(__name__)

_ETCD_FALLBACK_EXCEPTIONS = (
    RollingOpsEtcdctlError,
    RollingOpsEtcdNotConfiguredError,
    RollingOpsFileSystemError,
    RollingOpsNoEtcdRelationError,
    PebbleConnectionError,
)


class RollingOpsLockGrantedEvent(EventBase):
    """Custom event emitted when the background worker grants the lock."""


class RollingOpsEtcdFailedEvent(EventBase):
    """Custom event emitted when the etcd worker hits a fatal error."""


class RollingOpsManager(Object):
    def __init__(
        self,
        charm: CharmBase,
        peer_relation_name: str,
        etcd_relation_name: str,
        cluster_id: str,
        callback_targets: dict[str, Any],
        sync_lock_targets: dict[str, type[SyncLockBackend]] | None = None,
    ):
        super().__init__(charm, 'rolling-ops-manager')

        self.charm = charm
        self.peer_relation_name = peer_relation_name
        self.etcd_relation_name = etcd_relation_name
        self._sync_lock_targets = sync_lock_targets or {}
        charm.on.define_event('rollingops_lock_granted', RollingOpsLockGrantedEvent)
        charm.on.define_event('rollingops_etcd_failed', RollingOpsEtcdFailedEvent)

        self.peer_manager = PeerRollingOpsManager(
            charm=charm,
            relation_name=peer_relation_name,
            callback_targets=callback_targets,
        )
        self.etcd_manager = EtcdRollingOpsManager(
            charm=charm,
            peer_relation_name=peer_relation_name,
            etcd_relation_name=etcd_relation_name,
            cluster_id=cluster_id,
            callback_targets=callback_targets,
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_broken, self._on_etcd_relation_broken
        )
        self.framework.observe(charm.on.rollingops_lock_granted, self._on_rollingops_lock_granted)
        self.framework.observe(charm.on.rollingops_etcd_failed, self._on_rollingops_etcd_failed)
        # manage update status for etcd

    @property
    def _peer_relation(self) -> Relation | None:
        """Return the peer relation for this charm."""
        return self.model.get_relation(self.peer_relation_name)

    @property
    def _backend_state(self) -> UnitBackendState:
        return UnitBackendState(self.model, self.peer_relation_name, self.model.unit)

    def _on_etcd_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the etcd relation being fully removed.

        This method stops the etcd worker process since the required
        relation is no longer available.
        """
        self._fallback_current_unit_to_peer()

    def _select_processing_backend(self) -> ProcessingBackend:
        """Choose which backend should own new work for this unit."""
        if not self.etcd_manager.is_available():
            logger.info('etcd backend unavailable; selecting peer backend.')
            return ProcessingBackend.PEER

        if self._backend_state.is_peer_managed() and not self.peer_manager.has_pending_work():
            logger.info('etcd backend is available. Switching to etcd backend.')
            return ProcessingBackend.ETCD

        if self._backend_state.is_etcd_managed():
            logger.info('etcd backend selected.')
            return ProcessingBackend.ETCD

        logger.info('peer backend selected.')
        return ProcessingBackend.PEER

    def request_async_lock(
        self,
        callback_id: str,
        kwargs: dict[str, Any] | None = None,
        max_retry: int | None = None,
    ) -> None:
        """Create one operation, mirror it to backends, and trigger the active backend."""
        if callback_id not in self.peer_manager.callback_targets:
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
            self.peer_manager.enqueue_operation(operation)
        except (RollingOpsDecodingError, ValueError) as e:
            logger.error('Failed to persists operation in peer backend: %s', e)
            raise RollingOpsInvalidLockRequestError(
                'Failed to persists operation in peer backend.'
            ) from e

        if backend == ProcessingBackend.ETCD:
            try:
                self.etcd_manager.enqueue_operation(operation)
            except _ETCD_FALLBACK_EXCEPTIONS as e:
                logger.warning(
                    'Failed to persist operation in etcd backend; falling back to peer: %s',
                    e,
                )
                backend = ProcessingBackend.PEER

        if backend == ProcessingBackend.ETCD:
            self.etcd_manager.ensure_processing()
        else:
            self._fallback_current_unit_to_peer()

    def _fallback_current_unit_to_peer(self) -> None:
        self._backend_state.fallback_to_peer()
        self.etcd_manager.worker.stop()
        self.peer_manager.ensure_processing()

    def _on_rollingops_lock_granted(self, event: RollingOpsLockGrantedEvent) -> None:
        """Route the custom lock-granted event to the active backend.

        If the etcd backend fails during processing, switch this unit to peer
        and trigger peer processing.
        """
        if self._backend_state.is_peer_managed():
            logger.info('Executing rollingop on peer backend.')
            self.peer_manager._on_rollingops_lock_granted(event)
            return
        outcome = None
        try:
            logger.info('Executing rollingop on etcd backend.')
            outcome = self.etcd_manager._on_run_with_lock()
        except _ETCD_FALLBACK_EXCEPTIONS as e:
            logger.warning(
                'etcd backend failed while handling rollingops_lock_granted; '
                'falling back to peer: %s',
                e,
            )
            self._fallback_current_unit_to_peer()

        if (
            outcome is not None
            and outcome.executed
            and outcome.op_id is not None
            and outcome.result is not None
        ):
            try:
                self.peer_manager.mirror_result(outcome.op_id, outcome.result)
            except RollingOpsDecodingError:
                logger.info(
                    'Inconsistencies found between peer relation and etcd. '
                    'Falling back to peer backend.'
                )
                self._fallback_current_unit_to_peer()
                return
            logger.info('Execution mirrored to peer relation.')

    def _on_rollingops_etcd_failed(self, event: RollingOpsEtcdFailedEvent) -> None:
        """Fall back to peer when the etcd worker reports a fatal failure."""
        logger.warning('Received rollingops_etcd_failed; falling back to peer backend.')
        self._fallback_current_unit_to_peer()

    def _get_sync_lock_backend(self, backend_id: str) -> SyncLockBackend:
        """Resolve and instantiate a sync lock backend."""
        backend_cls = self._sync_lock_targets.get(backend_id, None)
        if backend_cls is None:
            raise RollingOpsSyncLockBackendError(f'Unknown sync lock backend: {backend_id}.')

        return backend_cls()

    @contextmanager
    def acquire_sync_lock(self, backend_id: str, timeout: int):
        """Acquire and release a sync lock backend around a critical section."""
        if self.etcd_manager.is_available():
            logger.info('Acquiring sync lock on etcd.')
            try:
                self.etcd_manager.acquire_sync_lock(timeout)
                yield
                return
            except Exception as e:
                logger.exception(
                    'Failed to request etcd sync lock; falling back to peer: %s',
                    e,
                )
            finally:
                try:
                    self.etcd_manager.release_sync_lock()
                    logger.info('etcd lock released.')
                except Exception as e:
                    logger.exception('Failed to release sync lock: %s', e)
            return

        backend = self._get_sync_lock_backend(backend_id)
        logger.info('Acquiring sync lock backend %s.', backend_id)
        try:
            backend.acquire(timeout=timeout)
        except Exception as e:
            raise RollingOpsSyncLockBackendError(
                f'Failed to acquire sync lock backend {backend_id}'
            ) from e

        try:
            yield
        finally:
            try:
                backend.release()
                logger.info('Sync lock backend %s released.', backend_id)
            except Exception as e:
                raise RollingOpsSyncLockBackendError(
                    f'Failed to release sync lock backend {backend_id}'
                ) from e

    @property
    def state(self) -> RollingOpsState:
        if self._peer_relation is None:
            return RollingOpsState(
                status=RollingOpsStatus.INVALID,
                processing_backend=None,
                operations=OperationQueue(),
            )

        operations = PeerUnitOperations(self.model, self.peer_relation_name, self.model.unit)

        status = self.peer_manager.get_status()
        if self._backend_state.is_etcd_managed():
            try:
                status = self.etcd_manager.get_status()
            except _ETCD_FALLBACK_EXCEPTIONS as e:
                logger.exception('Failed to get status: %s', e)
                self._fallback_current_unit_to_peer()
                status = self.peer_manager.get_status()

        return RollingOpsState(
            status=status,
            processing_backend=self._backend_state.backend,
            operations=operations.queue,
        )
