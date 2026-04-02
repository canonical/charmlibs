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
from sys import version_info

from ops import Relation
from ops.charm import CharmBase
from ops.framework import Object

from charmlibs import pathops
from charmlibs.rollingops.common._exceptions import RollingOpsCharmLibMissingError
from charmlibs.rollingops.common._models import with_pebble_retry

logger = logging.getLogger(__name__)

WORKER_PID_FIELD = 'etcd-rollingops-worker-pid'


class EtcdRollingOpsAsyncWorker(Object):
    """Spawns and manages the external rolling-ops worker process."""

    def __init__(self, charm: CharmBase, peer_relation_name: str, owner: str, cluster_id: str):
        super().__init__(charm, 'etcd-rollingops-async-worker')
        self._charm = charm
        self._peer_relation_name = peer_relation_name
        self._run_cmd = '/usr/bin/juju-exec'
        self._owner = owner
        self._charm_dir = charm.charm_dir
        self._cluster_id = cluster_id

    @property
    def _relation(self) -> Relation | None:
        return self.model.get_relation(self._peer_relation_name)

    def start(self) -> None:
        """Start a new worker process.

        Raises:
            RollingOpsCharmLibMissingError: if the lib files cannot be found.
        """
        if self._relation is None:
            return

        if pid_str := self._relation.data[self.model.unit].get(WORKER_PID_FIELD):
            try:
                pid = int(pid_str)
            except (ValueError, TypeError):
                pid = None

            if pid is not None and self._is_pid_alive(pid):
                logger.info(
                    'RollingOps worker already running with PID %s; not starting a new one.', pid
                )
                return

        # Remove JUJU_CONTEXT_ID so juju-run works from the spawned process
        new_env = os.environ.copy()
        new_env.pop('JUJU_CONTEXT_ID', None)

        venv_path = (
            self._charm_dir
            / 'venv'
            / 'lib'
            / f'python{version_info.major}.{version_info.minor}'
            / 'site-packages'
        )
        if not with_pebble_retry(lambda: venv_path.exists()):
            raise RollingOpsCharmLibMissingError(
                f'Expected virtualenv site-packages not found: {venv_path}'
            )

        for loc in new_env.get('PYTHONPATH', '').split(':'):
            path = pathops.LocalPath(loc)

            if path.stem != 'lib':
                continue
            new_env['PYTHONPATH'] = f'{venv_path.resolve()}:{new_env["PYTHONPATH"]}'
            break

        worker = venv_path / 'charmlibs' / 'rollingops' / 'etcd' / '_rollingops.py'
        if not with_pebble_retry(lambda: worker.exists()):
            raise RollingOpsCharmLibMissingError(f'Worker script not found: {worker}')

        # These files must stay open for the lifetime of the worker process.
        log_out = open('/var/log/etcd_rollingops_worker.log', 'a')  # noqa: SIM115
        log_err = open('/var/log/etcd_rollingops_worker.err', 'a')  # noqa: SIM115

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
                '--cluster-id',
                self._cluster_id,
            ],
            cwd=str(self._charm_dir),
            stdout=log_out,
            stderr=log_err,
            env=new_env,
        ).pid

        self._relation.data[self.model.unit].update({WORKER_PID_FIELD: str(pid)})
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

        pid_str = self._relation.data[self.model.unit].get(WORKER_PID_FIELD, '')

        try:
            pid = int(pid_str)
        except (TypeError, ValueError):
            logger.info('Missing PID or invalid PID found in the databag.')
            self._relation.data[self.model.unit].update({WORKER_PID_FIELD: ''})
            return

        try:
            os.kill(pid, signal.SIGTERM)
            logger.info('Sent SIGTERM to etcd rollingops worker process PID %s.', pid)
        except ProcessLookupError:
            logger.info('Process PID %s is already gone.', pid)
        except PermissionError:
            logger.warning('No permission to stop etcd rollingops worker process PID %s.', pid)
            return
        except OSError:
            logger.warning('SIGTERM failed for PID %s, attempting SIGKILL', pid)
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info('Sent SIGKILL to etcd rollingops worker process PID %s', pid)
            except ProcessLookupError:
                logger.info('Process PID %s exited before SIGKILL', pid)
            except PermissionError:
                logger.warning('No permission to SIGKILL process PID %s', pid)
                return
            except OSError:
                logger.warning('Failed to SIGKILL process PID %s', pid)
                return

        self._relation.data[self.model.unit].update({WORKER_PID_FIELD: ''})
