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
from typing import Any

from ops import Relation
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationCreatedEvent,
    RelationDepartedEvent,
)
from ops.framework import EventBase, Object

from charmlibs.rollingops.common._exceptions import (
    RollingOpsEtcdNotConfiguredError,
    RollingOpsInvalidLockRequestError,
    RollingOpsNoEtcdRelationError,
)
from charmlibs.rollingops.common._models import OperationResult
from charmlibs.rollingops.etcd import _etcdctl as etcdctl
from charmlibs.rollingops.etcd._etcd import EtcdLock, EtcdOperationQueue
from charmlibs.rollingops.etcd._models import EtcdOperation, RollingOpsKeys
from charmlibs.rollingops.etcd._relations import EtcdRequiresV1, SharedClientCertificateManager
from charmlibs.rollingops.etcd._worker import EtcdRollingOpsAsyncWorker

logger = logging.getLogger(__name__)


class EtcdRollingOpsManager(Object):
    """Rolling ops manager for clusters."""

    def __init__(
        self,
        charm: CharmBase,
        peer_relation_name: str,
        etcd_relation_name: str,
        cluster_id: str,
        callback_targets: dict[str, Any],
    ):
        """Register our custom events.

        params:
            charm: the charm we are attaching this to.
            peer_relation_name: peer relation used for rolling ops.
            etcd_relation_name: the relation to integrate with etcd.
            cluster_id: unique identifier for the cluster
            callback_targets: mapping from callback_id -> callable.
        """
        super().__init__(charm, 'etcd-rolling-ops-manager')
        self._charm = charm
        self.peer_relation_name = peer_relation_name
        self.etcd_relation_name = etcd_relation_name
        self.callback_targets = callback_targets
        self.charm_dir = charm.charm_dir

        owner = f'{self.model.uuid}-{self.model.unit.name}'.replace('/', '-')
        self.worker = EtcdRollingOpsAsyncWorker(
            charm, peer_relation_name=peer_relation_name, owner=owner, cluster_id=cluster_id
        )
        self.keys = RollingOpsKeys.for_owner(cluster_id, owner)

        self.shared_certificates = SharedClientCertificateManager(
            charm,
            peer_relation_name=peer_relation_name,
        )

        self.etcd = EtcdRequiresV1(
            charm,
            relation_name=etcd_relation_name,
            cluster_id=self.keys.cluster_prefix,
            shared_certificates=self.shared_certificates,
        )

        self.keys = RollingOpsKeys.for_owner(cluster_id=cluster_id, owner=owner)
        self.lock = EtcdLock(lock_key=self.keys.lock_key, owner=owner)
        self.pending_queue = EtcdOperationQueue(self.keys.pending, self.keys.lock_key, owner)
        self.inprogress_queue = EtcdOperationQueue(self.keys.inprogress, self.keys.lock_key, owner)

        self.framework.observe(
            charm.on[self.peer_relation_name].relation_departed, self._on_peer_relation_departed
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_broken, self._on_etcd_relation_broken
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_created, self._on_etcd_relation_created
        )

    @property
    def _peer_relation(self) -> Relation | None:
        """Return the peer relation for this charm."""
        return self.model.get_relation(self.peer_relation_name)

    @property
    def _etcd_relation(self) -> Relation | None:
        """Return the etcd relation for this charm."""
        return self.model.get_relation(self.etcd_relation_name)

    def _on_etcd_relation_created(self, event: RelationCreatedEvent) -> None:
        """Check whether the snap-provided etcdctl command is available."""
        if not etcdctl.is_etcdctl_installed():
            logger.error('%s is not installed', etcdctl.ETCDCTL_CMD)
            # TODO: fallback to peer relation implementation.

    def _on_rollingops_lock_granted(self, event: EventBase) -> None:
        """Handle the event when a rolling operation lock is granted.

        If etcd is not yet configured, the operation is skipped.
        """
        if not self._peer_relation or not self._etcd_relation:
            # TODO: handle this case. Fallback to peer relation.
            return
        try:
            etcdctl.ensure_initialized()
        except RollingOpsEtcdNotConfiguredError:
            # TODO: handle this case. Fallback to peer relation.
            return
        logger.info('Received a rolling-op lock granted event.')
        self._on_run_with_lock()

    def _on_peer_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Handle a unit departing from the peer relation.

        If the current unit is the one departing, stop the etcd worker
        process to ensure a clean shutdown.
        """
        unit = event.departing_unit
        if unit == self.model.unit:
            self.worker.stop()

    def _on_etcd_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the etcd relation being fully removed.

        This method stops the etcd worker process since the required
        relation is no longer available.
        """
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

        etcdctl.ensure_initialized()

        if kwargs is None:
            kwargs = {}

        operation = EtcdOperation.create(callback_id, kwargs, max_retry)
        res = self.pending_queue.enqueue(operation)

        if res:
            self.worker.start()
        else:
            logger.info('Operation %s already exists in the queue.', operation.callback_id)

    def _on_run_with_lock(self) -> None:
        """Execute the current operation while holding the distributed lock.

        This method is triggered when the worker determines that the current
        unit owns the distributed lock. The method retrieves the head operation
        from the in-progress queue and executes its registered callback.

        After execution, the operation is moved to the completed queue and its
        updated state is persisted.
        """
        if not self.lock.is_held():
            logger.info('Lock is not granted. Operation will not run.')
            return

        if not (operation := self.inprogress_queue.peek()):
            logger.info('Lock granted but there is no operation to run.')
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
                operation.retry_hold()

            case OperationResult.RETRY_RELEASE:
                logger.info('Finished %s. Operation will be retried later.', operation.callback_id)
                operation.retry_release()

            case _:
                logger.info('Finished %s. Lock will be released.', operation.callback_id)
                operation.complete()

        moved = self.inprogress_queue.move_operation(self.keys.completed, operation)
        logger.info('moved %s', moved)
