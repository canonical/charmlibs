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
import subprocess
from typing import Any

from ops import Relation
from ops.charm import CharmBase, RelationBrokenEvent, RelationDepartedEvent
from ops.framework import EventBase, Object

logger = logging.getLogger(__name__)

from charmlibs.advanced_rollingops._etcdctl import EtcdCtl
from charmlibs.advanced_rollingops._models import (
    RollingOpsEtcdNotConfiguredError,
    RollingOpsKeys,
    RollingOpsNoEtcdRelationError,
)
from charmlibs.advanced_rollingops._relations import EtcdRequiresV1, SharedClientCertificateManager
from charmlibs.advanced_rollingops._worker import EtcdRollingOpsAsyncWorker


class RollingOpsLockGrantedEvent(EventBase):
    """Custom event emitted when the background worker grants the lock."""


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
        super().__init__(charm, 'rolling-ops-manager')
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

        charm.on.define_event('rollingops_lock_granted', RollingOpsLockGrantedEvent)

        self.framework.observe(
            charm.on[self.peer_relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_broken, self._on_relation_broken
        )
        self.framework.observe(charm.on.rollingops_lock_granted, self._on_rollingop_granted)
        self.framework.observe(charm.on.install, self._on_install)

    @property
    def _peer_relation(self) -> Relation | None:
        return self.model.get_relation(self.peer_relation_name)

    @property
    def _etcd_relation(self) -> Relation | None:
        return self.model.get_relation(self.etcd_relation_name)

    def _on_install(self, event) -> None:
        subprocess.run(['apt-get', 'update'], check=True)
        subprocess.run(['apt-get', 'install', '-y', 'etcd-client'], check=True)

    def _on_rollingop_granted(self, event: RollingOpsLockGrantedEvent) -> None:
        if not self._peer_relation or not self._etcd_relation:
            return
        try:
            EtcdCtl.ensure_initialized()
        except RollingOpsEtcdNotConfiguredError:
            return
        logger.info('Received a rolling-op lock granted event.')
        self._on_run_with_lock()

    def _on_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Stop the etcd worker process in the current unit."""
        unit = event.departing_unit
        if unit == self.model.unit:
            self.worker.stop()

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Stop the etcd worker process in the current unit."""
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
            ValueError: If the callback_id is not registered or invalid parameters
            RollingOpsNoEtcdRelationError: if the etcd relation does not exist
            RollingOpsEtcdNotConfiguredError: if etcd client has not been configured yet
        """
        if callback_id not in self.callback_targets:
            raise ValueError(f'Unknown callback_id: {callback_id}')

        etcd_relation = self.model.get_relation(self.etcd_relation_name)
        if not etcd_relation:
            raise RollingOpsNoEtcdRelationError

        EtcdCtl.ensure_initialized()

        self.worker.start()

    def _on_run_with_lock(self) -> None:
        """Execute the current operation while holding the distributed lock.

        This method is triggered when the worker determines that the current
        unit owns the distributed lock. The method retrieves the head operation
        from the in-progress queue and executes its registered callback.

        After execution, the operation is moved to the completed queue and its
        updated state is persisted.
        """
        EtcdCtl.run(['put', self.keys.lock_key, self.keys.owner])

        proc = EtcdCtl.run(['get', self.keys.lock_key, '--print-value-only'], check=False)

        if proc.returncode != 0:
            return False

        value = proc.stdout.strip()
        if value != self.keys.owner:
            logger.info('Callback not executed.')

        callback = self.callback_targets.get('_restart', '')
        callback(delay=1)
