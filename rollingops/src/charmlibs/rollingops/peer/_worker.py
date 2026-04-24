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

from ops import RelationDataContent
from ops.charm import (
    CharmBase,
)

from charmlibs import pathops
from charmlibs.rollingops.common._base_worker import BaseRollingOpsAsyncWorker

logger = logging.getLogger(__name__)

PEER_LOG_FILENAME = 'peer_rollingops_worker.log'
WORKER_PID_FIELD = 'peer-rollingops-worker-pid'


class PeerRollingOpsAsyncWorker(BaseRollingOpsAsyncWorker):
    """Manage the peer-backed rolling-ops worker process.

    The worker state is coordinated through the peer relation application
    databag to ensure that it remains accessible across leadership
    changes. This guarantees that a newly elected leader can detect,
    stop, or restart an existing worker process as needed.
    """

    _pid_field = WORKER_PID_FIELD
    _log_filename = PEER_LOG_FILENAME

    def __init__(self, charm: CharmBase, relation_name: str, base_dir: pathops.LocalPath):
        super().__init__(
            charm,
            'peer-rollingops-async-worker',
            relation_name,
            base_dir=base_dir,
        )

    @property
    def _app_data(self) -> RelationDataContent:
        """Return the application databag in the peer relation."""
        return self._relation.data[self.model.app]  # type: ignore[reportOptionalMemberAccess]

    def _worker_script_path(self) -> pathops.LocalPath:
        """Return the path to the peer rolling-ops worker script.

        This script is executed in a background process to handle operation
        processing for the peer backend.
        """
        return pathops.LocalPath(
            self._venv_site_packages() / 'charmlibs' / 'rollingops' / 'peer' / '_rollingops.py'
        )

    @property
    def _pid(self) -> int | None:
        """Return the stored worker process PID.

        The PID is persisted in the application databag of the peer relation.

        Returns:
            The worker process PID, or None if not set.
        """
        if self._relation is None:
            return None
        pid = self._app_data.get(self._pid_field, '')

        try:
            pid = int(pid)
        except (ValueError, TypeError):
            pid = None

        return pid

    @_pid.setter
    def _pid(self, value: int | None) -> None:
        """Persist the worker process PID in the peer relation databag.

        The PID is stored in the application databag because it is used
        to trigger rolling operations on the leader and the leader may change.

        Args:
            value: The process identifier to store.
        """
        if self._relation is None:
            return
        self._app_data.update({self._pid_field: '' if value is None else str(value)})

    def _on_existing_worker(self, pid: int) -> bool:
        """Handle the presence of an already running worker process.

        When an existing worker is detected, it is stopped before starting a
        new one to ensure a single active worker per application.

        Args:
            pid: The PID of the currently running worker.

        Returns:
            True to indicate that the existing worker was handled and a new
            worker can be started.
        """
        logger.info('Stopping existing RollingOps worker PID %s before restart.', pid)
        self.stop()
        return True
