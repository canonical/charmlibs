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
import os
import signal
import subprocess
from pathlib import Path
from sys import version_info

from ops import Relation, RelationDataContent
from ops.charm import (
    CharmBase,
)
from ops.framework import Object

logger = logging.getLogger(__name__)


class PeerRollingOpsAsyncWorker(Object):
    """Spawns and manages the external rolling-ops worker process."""

    def __init__(self, charm: CharmBase, relation_name: str):
        super().__init__(charm, 'peer-rollingops-async-worker')
        self._charm = charm
        self._peers_name = relation_name
        self._run_cmd = '/usr/bin/juju-exec'
        self._charm_dir = charm.charm_dir

    @property
    def _relation(self) -> Relation | None:
        """Returns the peer relation."""
        return self._charm.model.get_relation(self._peers_name)

    @property
    def _app_data(self) -> RelationDataContent:
        """Returns the application databag in the peer relation."""
        return self._relation.data[self.model.app]  # type: ignore[reportOptionalMemberAccess]

    def start(self) -> None:
        """Start a new worker process."""
        if self._relation is None:
            return
        self.stop()

        # Remove JUJU_CONTEXT_ID so juju-run works from the spawned process
        new_env = os.environ.copy()
        new_env.pop('JUJU_CONTEXT_ID', None)

        for loc in new_env.get('PYTHONPATH', '').split(':'):
            path = Path(loc)
            venv_path = (
                path
                / '..'
                / 'venv'
                / 'lib'
                / f'python{version_info.major}.{version_info.minor}'
                / 'site-packages'
            )
            if path.stem == 'lib':
                new_env['PYTHONPATH'] = f'{venv_path.resolve()}:{new_env["PYTHONPATH"]}'
                break

        worker = (
            self._charm_dir
            / 'venv'
            / 'lib'
            / f'python{version_info.major}.{version_info.minor}'
            / 'site-packages'
            / 'charmlibs'
            / 'rollingops'
            / '_peer_rollingops.py'
        )

        # These files must stay open for the lifetime of the worker process.
        log_out = open('/var/log/peer_rollingops_worker.log', 'a')  # noqa: SIM115
        log_err = open('/var/log/peer_rollingops_worker.err', 'a')  # noqa: SIM115

        pid = subprocess.Popen(
            [
                '/usr/bin/python3',
                '-u',
                str(worker),
                '--run-cmd',
                self._run_cmd,
                '--unit-name',
                self._charm.model.unit.name,
                '--charm-dir',
                str(self._charm_dir),
            ],
            cwd=str(self._charm_dir),
            stdout=log_out,
            stderr=log_err,
            env=new_env,
        ).pid

        self._app_data.update({'rollingops-worker-pid': str(pid)})
        logger.info('Started RollingOps worker process with PID %s', pid)

    def stop(self) -> None:
        """Stop the running worker process if it exists."""
        if self._relation is None:
            return

        if not (pid_str := self._app_data.get('rollingops-worker-pid', '')):
            return

        pid = int(pid_str)
        try:
            os.kill(pid, signal.SIGINT)
            logger.info('Stopped RollingOps worker process PID %s', pid)
        except OSError:
            logger.info('Failed to stop RollingOps worker process PID %s', pid)

        self._app_data.update({'rollingops-worker-pid': ''})
