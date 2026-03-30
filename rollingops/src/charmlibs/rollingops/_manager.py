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

from charmlibs.rollingops import _etcdctl as etcdctl
from charmlibs.rollingops._models import (
    RollingOpsEtcdNotConfiguredError,
    RollingOpsInvalidLockRequestError,
    RollingOpsKeys,
    RollingOpsNoEtcdRelationError,
)
from charmlibs.rollingops._relations import EtcdRequiresV1, SharedClientCertificateManager
from charmlibs.rollingops._worker import EtcdRollingOpsAsyncWorker

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
            charm, peer_relation_name=peer_relation_name, owner=owner
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

        self.framework.observe(
            charm.on[self.peer_relation_name].relation_departed, self._on_peer_relation_departed
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_broken, self._on_etcd_relation_broken
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_created, self._on_etcd_relation_created
        )
        self.framework.observe(charm.on.rollingops_lock_granted, self._on_rollingop_granted)

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

    def _on_rollingop_granted(self, event) -> None:
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
        """This is a dummy function.

        Here we spawn a new process that will trigger a Juju hook.
        This function will be completely remade in the next PR.

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

        # TODO: implement actual lock request

        self.worker.start()

    def _on_run_with_lock(self) -> None:
        """This is a dummy function.

        Here we try to reach etcd from each unit.
        This function will be completely remade in the next PR.
        """
        # TODO: implement the actual execution under lock
        etcdctl.run(['put', self.keys.lock_key, self.keys.owner])

        result = etcdctl.run(['get', self.keys.lock_key, '--print-value-only'])

        if result is None:
            logger.error('Unexpected response from etcd.')
            return

        callback = self.callback_targets.get('_restart', '')
        callback(delay=1)
