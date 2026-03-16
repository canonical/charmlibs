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
import os
import signal
import subprocess
from pathlib import Path
from sys import version_info

from ops.charm import CharmBase
from ops.framework import Object

logger = logging.getLogger(__name__)


class EtcdRollingOpsAsyncWorker(Object):
    """Spawns and manages the external rolling-ops worker process."""

    def __init__(self, charm: CharmBase, peer_relation_name: str, owner: str):
        super().__init__(charm, 'etcd-ollingops-async-worker')
        self._charm = charm
        self._peer_relation_name = peer_relation_name
        self._run_cmd = '/usr/bin/juju-exec'
        self._owner = owner
        self._charm_dir = charm.charm_dir

    @property
    def _relation(self):
        return self.model.get_relation(self._peer_relation_name)

    @property
    def _unit_data(self):
        return self._relation.data[self.model.unit]

    def start(self) -> None:
        """Start a new worker process."""
        if self._relation is None:
            return

        pid_str = self._unit_data.get('etcd-rollingops-worker-pid', '')
        if pid_str:
            try:
                pid = int(pid_str)
            except ValueError:
                pid = -1

            if self._is_pid_alive(pid):
                logger.info(
                    'RollingOps worker already running with PID %s; not starting a new one.', pid
                )
                return

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
            / f'venv/lib/python{version_info.major}.{version_info.minor}/site-packages/charmlibs/advanced_rollingops'
            / '_etcd_rollingops.py'
        )

        pid = subprocess.Popen(
            [
                '/usr/bin/python3',
                '-u',
                str(worker),
                '--run-cmd',
                self._run_cmd,
                '--unit-name',
                self.model.unit.name,
                '--charm-dir',
                str(self._charm_dir),
                '--owner',
                self._owner,
            ],
            cwd=str(self._charm_dir),
            stdout=open('/var/log/etcd_rollingops_worker.log', 'a'),
            stderr=open('/var/log/etcd_rollingops_worker.err', 'a'),
            env=new_env,
        ).pid

        self._unit_data.update({'etcd-rollingops-worker-pid': str(pid)})
        logger.info('Started etcd rollingops worker process with PID %s', pid)

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def stop(self) -> None:
        """Stop the running worker process if it exists."""
        if self._relation is None:
            return
        pid_str = self._unit_data.get('etcd-rollingops-worker-pid', '')
        if not pid_str:
            return

        pid = int(pid_str)
        try:
            os.kill(pid, signal.SIGINT)
            logger.info('Stopped etcd rollingops worker process PID %s', pid)
        except OSError:
            logger.info('Failed to stop etcd rollingops worker process PID %s', pid)
            pass
        self._unit_data.update({'etcd-rollingops-worker-pid': ''})
