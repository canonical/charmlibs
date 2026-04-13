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
    """Manage the etcd-backed rolling-ops worker process.

    Unlike the peer backend, each unit runs its own worker process when
    using the etcd backend. Worker PID is stored in the unit databag,
    ensuring isolation between units and allowing each unit to independently
    manage its own worker lifecycle.
    """

    _pid_field = WORKER_PID_FIELD
    _log_filename = 'etcd_rollingops_worker'

    def __init__(self, charm: CharmBase, peer_relation_name: str, owner: str, cluster_id: str):
        super().__init__(charm, 'etcd-rollingops-async-worker', peer_relation_name)
        self._owner = owner
        self._cluster_id = cluster_id

    def _worker_script_path(self) -> pathops.LocalPath:
        """Return the path to the etcd rolling-ops worker script.

        This script is executed in a background process to handle operation
        processing for the etcd backend.
        """
        return pathops.LocalPath(
            self._venv_site_packages() / 'charmlibs' / 'rollingops' / 'etcd' / '_rollingops.py'
        )

    def _worker_args(self) -> list[str]:
        """Return the arguments passed to the etcd worker process.

        Returns:
            A list of command-line arguments for the worker process.
        """
        return [
            '--owner',
            self._owner,
            '--cluster-id',
            self._cluster_id,
        ]

    def _get_pid_str(self) -> str:
        """Return the stored worker process PID for this unit.

        The PID is stored in the unit databag because each unit runs its own
        independent worker process when using the etcd backend. This ensures
        that worker lifecycle management is isolated per unit.

        Returns:
            The worker process PID as a string, or an empty string if not set.
        """
        if self._relation is None:
            return ''
        return self._relation.data[self.model.unit].get(self._pid_field, '')

    def _set_pid_str(self, pid: str) -> None:
        """Persist the worker process PID in the unit databag.

        The PID is stored per unit to reflect that each unit owns and manages
        its own worker process when using the etcd backend.

        Args:
            pid: The process identifier to store.
        """
        if self._relation is None:
            return
        self._relation.data[self.model.unit].update({self._pid_field: pid})

    def _on_existing_worker(self, pid: int) -> bool:
        """Executed on detection of an already running worker for this unit.

        Since each unit manages its own worker process, an existing worker is
        considered valid and is left running. No restart is performed.

        Args:
            pid: The PID of the currently running worker.

        Returns:
            False to indicate that no new worker should be started.
        """
        logger.info(
            'RollingOps worker already running with PID %s; not starting a new one.',
            pid,
        )
        return False
