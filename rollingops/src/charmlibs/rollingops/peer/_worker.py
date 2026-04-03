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


class PeerRollingOpsAsyncWorker(BaseRollingOpsAsyncWorker):
    """Manage the peer-backed rolling-ops worker process."""

    _pid_field = 'peer-rollingops-worker-pid'
    _log_filename = 'peer_rollingops_worker'

    def __init__(self, charm: CharmBase, relation_name: str):
        super().__init__(charm, 'peer-rollingops-async-worker', relation_name)

    @property
    def _app_data(self) -> RelationDataContent:
        """Return the application databag in the peer relation."""
        return self._relation.data[self.model.app]  # type: ignore[reportOptionalMemberAccess]

    def _worker_script_path(self) -> pathops.LocalPath:
        return pathops.LocalPath(
            self._venv_site_packages() / 'charmlibs' / 'rollingops' / 'peer' / '_rollingops.py'
        )

    def _get_pid_str(self) -> str:
        if self._relation is None:
            return ''
        return self._app_data.get(self._pid_field, '')

    def _set_pid_str(self, pid: str) -> None:
        if self._relation is None:
            return
        self._app_data.update({self._pid_field: pid})

    def _on_existing_worker(self, pid: int) -> bool:
        logger.info('Stopping existing RollingOps worker PID %s before restart.', pid)
        self.stop()
        return True
