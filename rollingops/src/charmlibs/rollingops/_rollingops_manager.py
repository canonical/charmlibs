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

"""etcd rolling ops."""

import logging
from typing import Any

from ops import CharmBase, Object, Relation
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
)
from charmlibs.rollingops.common._models import (
    Operation,
    ProcessingBackend,
    RollingOpsStatus,
    UnitBackendState,
)
from charmlibs.rollingops.etcd._manager import EtcdRollingOpsManager
from charmlibs.rollingops.peer._manager import PeerRollingOpsManager
from charmlibs.rollingops.peer._models import OperationQueue, PeerUnitOperations, RollingOpsState

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
    ):
        super().__init__(charm, 'rolling-ops-manager')

        self.charm = charm
        self.peer_relation_name = peer_relation_name
        self.etcd_relation_name = etcd_relation_name
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

        self.framework.observe(charm.on.rollingops_lock_granted, self._on_rollingops_lock_granted)
        self.framework.observe(charm.on.rollingops_etcd_failed, self._on_rollingops_etcd_failed)
        # manage update status for etcd

    @property
    def _peer_relation(self) -> Relation | None:
        """Return the peer relation for this charm."""
        return self.model.get_relation(self.peer_relation_name)

    @property
    def _etcd_relation(self) -> Relation | None:
        """Return the etcd relation for this charm."""
        return self.model.get_relation(self.etcd_relation_name)

    @property
    def _backend_state(self) -> UnitBackendState:
        return UnitBackendState(self.model, self.peer_relation_name, self.model.unit)

    def _has_relation(self, relation_name: str) -> bool:
        return self.model.get_relation(relation_name) is not None

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
            self.peer_manager._on_run_with_lock()
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
            self.peer_manager.mirror_result(outcome.op_id, outcome.result)
            logger.info('Execution mirrored to peer relation.')

    def _on_rollingops_etcd_failed(self, event: RollingOpsEtcdFailedEvent) -> None:
        """Fall back to peer when the etcd worker reports a fatal failure."""
        logger.warning('Received rollingops_etcd_failed; falling back to peer backend.')
        self._fallback_current_unit_to_peer()

    def request_sync_lock(self, timeout: int) -> bool:
        """Try to acquire the lock until timeout expires.

        Args:
            timeout: Maximum time in seconds to wait for the lock.

        Returns:
            True if the lock was granted. False otherwise.
        """
        if self.etcd_manager.is_available():
            try:
                return self.etcd_manager.request_sync_lock(timeout)
            except _ETCD_FALLBACK_EXCEPTIONS as e:
                logger.exception(
                    'Failed to request etcd sync lock; falling back to peer: %s',
                    e,
                )

        return self.peer_manager.request_sync_lock(timeout)

    def release_sync_lock(self) -> None:
        """Release the lock and revoke the associated lease."""
        if not self.etcd_manager.is_sync_lock_used():
            self.peer_manager.release_sync_lock()
            return
        try:
            self.etcd_manager.release_sync_lock()
        except _ETCD_FALLBACK_EXCEPTIONS as e:
            logger.exception(
                'Failed to release sync lock: %s',
                e,
            )

    @property
    def state(self) -> RollingOpsState:
        if self._peer_relation is None:
            return RollingOpsState(
                status=RollingOpsStatus.NOT_INITIALIZED,
                processing_backend=None,
                operations=OperationQueue(),
            )

        operations = PeerUnitOperations(self.model, self.peer_relation_name, self.model.unit)

        status = self.peer_manager.get_status()
        if self._backend_state.is_etcd_managed():
            try:
                status = self.etcd_manager.get_status()
            except _ETCD_FALLBACK_EXCEPTIONS as e:
                logger.exception(
                    'Failed to release sync lock: %s',
                    e,
                )
                self._fallback_current_unit_to_peer()

        return RollingOpsState(
            status=status,
            processing_backend=self._backend_state.backend,
            operations=operations.queue,
        )
