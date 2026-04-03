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

from ops.charm import CharmBase

from charmlibs import pathops
from charmlibs.rollingops.common._base_worker import BaseRollingOpsAsyncWorker

logger = logging.getLogger(__name__)

WORKER_PID_FIELD = 'etcd-rollingops-worker-pid'


class EtcdRollingOpsAsyncWorker(BaseRollingOpsAsyncWorker):
    """Manage the etcd-backed rolling-ops worker process."""

    _pid_field = WORKER_PID_FIELD
    _log_filename = 'etcd_rollingops_worker'

    def __init__(self, charm: CharmBase, peer_relation_name: str, owner: str, cluster_id: str):
        super().__init__(charm, 'etcd-rollingops-async-worker', peer_relation_name)
        self._owner = owner
        self._cluster_id = cluster_id

    def _worker_script_path(self) -> pathops.LocalPath:
        return pathops.LocalPath(
            self._venv_site_packages() / 'charmlibs' / 'rollingops' / 'etcd' / '_rollingops.py'
        )

    def _worker_args(self) -> list[str]:
        return [
            '--owner',
            self._owner,
            '--cluster-id',
            self._cluster_id,
        ]

    def _get_pid_str(self) -> str:
        if self._relation is None:
            return ''
        return self._relation.data[self.model.unit].get(self._pid_field, '')

    def _set_pid_str(self, pid: str) -> None:
        if self._relation is None:
            return
        self._relation.data[self.model.unit].update({self._pid_field: pid})

    def _on_existing_worker(self, pid: int) -> bool:
        logger.info(
            'RollingOps worker already running with PID %s; not starting a new one.',
            pid,
        )
        return False
