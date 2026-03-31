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

"""etcd rolling ops. Spawns and manages the external rolling-ops worker process."""

import logging
from typing import Any

from ops import CharmBase, Object
from ops.framework import EventBase

from charmlibs.rollingops._manager import EtcdRollingOpsManager
from charmlibs.rollingops._peer_manager import PeerRollingOpsManager

logger = logging.getLogger(__name__)


class RollingOpsLockGrantedEvent(EventBase):
    """Custom event emitted when the background worker grants the lock."""


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

    def _has_relation(self, relation_name: str) -> bool:
        return self.model.get_relation(relation_name) is not None

    def _get_active_manager(self) -> Any:
        has_etcd = self._has_relation(self.etcd_relation_name)
        has_peer = self._has_relation(self.peer_relation_name)

        if has_etcd:
            return self.etcd_manager

        if has_peer:
            return self.peer_manager

        raise RuntimeError('No active rollingops relation found.')

    def request_async_lock(
        self, callback_id: str, kwargs: dict[str, Any] | None = None, max_retry: int | None = None
    ) -> None:
        manager = self._get_active_manager()
        return manager.request_async_lock(
            callback_id=callback_id, kwargs=kwargs, max_retry=max_retry
        )

    def _on_rollingops_lock_granted(self, event: RollingOpsLockGrantedEvent) -> None:
        """Handler of the custom hook rollingops_lock_granted.

        The custom hook is triggered by a background process.
        """
        manager = self._get_active_manager()
        manager._on_rollingops_lock_granted(event)
