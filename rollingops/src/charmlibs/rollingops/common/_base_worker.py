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

"""Common class to manager background processes."""

import logging
import os
import signal
import subprocess
from sys import version_info

from ops import CharmBase, Object, Relation

from charmlibs import pathops
from charmlibs.rollingops.common._exceptions import RollingOpsCharmLibMissingError
from charmlibs.rollingops.common._models import with_pebble_retry

logger = logging.getLogger(__name__)


class BaseRollingOpsAsyncWorker(Object):
    """Base class for external rolling-ops worker processes."""

    _run_cmd = '/usr/bin/juju-exec'
    _pid_field: str
    _log_filename: str

    def __init__(self, charm: CharmBase, handle_name: str, relation_name: str):
        super().__init__(charm, handle_name)
        self._charm = charm
        self._charm_dir = charm.charm_dir
        self._relation_name = relation_name

    @property
    def _relation(self) -> Relation | None:
        """Return the peer relation."""
        return self._charm.model.get_relation(self._relation_name)

    def _venv_site_packages(self) -> pathops.LocalPath:
        """Return the charm virtualenv site-packages path."""
        return pathops.LocalPath(
            self._charm_dir
            / 'venv'
            / 'lib'
            / f'python{version_info.major}.{version_info.minor}'
            / 'site-packages'
        )

    def _build_env(self) -> dict[str, str]:
        """Build the environment for the spawned worker."""
        new_env = os.environ.copy()
        new_env.pop('JUJU_CONTEXT_ID', None)

        venv_path = self._venv_site_packages()

        for loc in new_env.get('PYTHONPATH', '').split(':'):
            path = pathops.LocalPath(loc)

            if path.stem != 'lib':
                continue
            new_env['PYTHONPATH'] = f'{venv_path.resolve()}:{new_env["PYTHONPATH"]}'
            break
        return new_env

    def _worker_script_path(self) -> pathops.LocalPath:
        """Return the worker script path."""
        raise NotImplementedError

    def _worker_args(self) -> list[str]:
        """Return backend-specific worker CLI args."""
        return []

    def _get_pid_str(self) -> str:
        """Return the stored worker PID string."""
        raise NotImplementedError

    def _set_pid_str(self, pid: str) -> None:
        """Persist the worker PID string."""
        raise NotImplementedError

    def _on_existing_worker(self, pid: int) -> bool:
        """Handle case where a worker is already running.

        Returns:
            True if a new worker should be started,
            False if start() should return early.
        """
        raise NotImplementedError

    def _validate_startup_paths(self) -> None:
        """Validate any paths before starting."""
        venv_path = self._venv_site_packages()
        if not with_pebble_retry(lambda: venv_path.exists()):
            raise RollingOpsCharmLibMissingError(
                f'Expected virtualenv site-packages not found: {venv_path}'
            )

        worker = self._worker_script_path()
        if not with_pebble_retry(lambda: worker.exists()):
            raise RollingOpsCharmLibMissingError(f'Worker script not found: {worker}')

    def _is_pid_alive(self, pid: int) -> bool:
        """Return whether the given PID appears to be alive."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def start(self) -> None:
        """Start a new worker process if one is not already running."""
        pid_str = self._get_pid_str()
        if pid_str:
            try:
                pid = int(pid_str)
            except (ValueError, TypeError):
                pid = None

            if pid is not None and self._is_pid_alive(pid) and not self._on_existing_worker(pid):
                return

        self._validate_startup_paths()

        worker = self._worker_script_path()
        env = self._build_env()

        log_out = open(f'/var/log/{self._log_filename}.log', 'a')  # noqa: SIM115
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
                *self._worker_args(),
            ],
            cwd=str(self._charm_dir),
            stdout=log_out,
            stderr=log_out,
            env=env,
        ).pid

        self._set_pid_str(str(pid))
        logger.info('Started rollingops worker process with PID %s', pid)

    def stop(self) -> None:
        """Stop the running worker process if it exists."""
        pid_str = self._get_pid_str()

        try:
            pid = int(pid_str)
        except (TypeError, ValueError):
            logger.info('Missing PID or invalid PID found in worker state.')
            self._set_pid_str('')
            return

        try:
            os.kill(pid, signal.SIGTERM)
            logger.info('Sent SIGTERM to rollingops worker process PID %s.', pid)
        except ProcessLookupError:
            logger.info('Process PID %s is already gone.', pid)
        except PermissionError:
            logger.warning('No permission to stop rollingops worker process PID %s.', pid)
            return
        except OSError:
            logger.warning('SIGTERM failed for PID %s, attempting SIGKILL', pid)
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info('Sent SIGKILL to rollingops worker process PID %s', pid)
            except ProcessLookupError:
                logger.info('Process PID %s exited before SIGKILL', pid)
            except PermissionError:
                logger.warning('No permission to SIGKILL process PID %s', pid)
                return
            except OSError:
                logger.warning('Failed to SIGKILL process PID %s', pid)
                return

        self._set_pid_str('')
