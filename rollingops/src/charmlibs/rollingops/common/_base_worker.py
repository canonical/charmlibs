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
from charmlibs.rollingops.common._exceptions import RollingOpsLibMissingError
from charmlibs.rollingops.common._utils import with_pebble_retry

logger = logging.getLogger(__name__)


class BaseRollingOpsAsyncWorker(Object):
    """Base class for external rolling-ops worker processes.

    This class provides the common lifecycle management for background
    worker processes used by rolling-ops backends. It is responsible for:

    - locating the worker script inside the charm virtualenv
    - building the execution environment for the subprocess
    - validating required files before startup
    - starting and stopping the worker process
    - persisting and retrieving the worker PID through backend-specific storage

    Subclasses define where worker state is stored, how existing workers
    should be handled, and which worker script and arguments should be used.
    """

    _pid_field: str
    _log_filename: str

    def __init__(self, charm: CharmBase, handle_name: str, peer_relation_name: str):
        """Initialize the base rolling-ops worker helper.

        Args:
            charm: The charm instance managing the worker process.
            handle_name: Framework handle name used for this worker object.
            peer_relation_name: Name of the peer relation used by subclasses
                to store and retrieve worker state.
        """
        super().__init__(charm, handle_name)
        self._charm = charm
        self._charm_dir = charm.charm_dir
        self._peer_relation_name = peer_relation_name
        self._handle_name = handle_name

    @property
    def _relation(self) -> Relation | None:
        """Return the peer relation used for worker state."""
        return self._charm.model.get_relation(self._peer_relation_name)

    def _venv_site_packages(self) -> pathops.LocalPath:
        """Return the site-packages path for the charm virtualenv.

        This path is used to locate the rolling-ops worker scripts and ensure
        the spawned subprocess can import charm library code.
        """
        return pathops.LocalPath(
            self._charm_dir
            / 'venv'
            / 'lib'
            / f'python{version_info.major}.{version_info.minor}'
            / 'site-packages'
        )

    def _build_env(self) -> dict[str, str]:
        """Build the environment used to spawn the worker subprocess.

        The worker runs outside the current Juju hook context, so the Juju
        context identifier is removed from the environment. The charm virtualenv
        site-packages path is also prepended to ``PYTHONPATH`` so that the
        worker can import charm libraries correctly.

        Returns:
            A copy of the current environment adjusted for the worker process.
        """
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
        """Return additional backend-specific command-line arguments.

        Subclasses may override this to pass extra arguments required by the
        worker process.

        Returns:
            A list of command-line arguments to append when starting the worker.
        """
        return []

    def _get_pid_str(self) -> str:
        """Return the stored worker PID string.

        Returns:
            The stored PID as a string, or an empty string if no PID is stored.

        Raises:
            NotImplementedError: If not implemented by a subclass.
        """
        raise NotImplementedError

    def _set_pid_str(self, pid: str) -> None:
        """Persist the worker PID string.

        Args:
            pid: The PID string to persist. An empty string clears the stored PID.

        Raises:
            NotImplementedError: If not implemented by a subclass.
        """
        raise NotImplementedError

    def _on_existing_worker(self, pid: int) -> bool:
        """Handle case where a worker is already running.

        Returns:
            True if a new worker should be started,
            False if start() should return early.
        """
        raise NotImplementedError

    def _validate_startup_paths(self) -> None:
        """Validate that the worker runtime files exist before startup.

        This checks that the charm virtualenv site-packages directory exists
        and that the backend-specific worker script is present.

        Raises:
            RollingOpsLibMissingError: If the virtualenv or worker script
                cannot be found.
        """
        venv_path = self._venv_site_packages()
        if not with_pebble_retry(lambda: venv_path.exists()):
            raise RollingOpsLibMissingError(
                f'Expected virtualenv site-packages not found: {venv_path}'
            )

        worker = self._worker_script_path()
        if not with_pebble_retry(lambda: worker.exists()):
            raise RollingOpsLibMissingError(f'Worker script not found: {worker}')

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
        """Start the worker subprocess if one is not already running.

        Raises:
            RollingOpsLibMissingError: If the virtualenv or worker script
                required to start the worker is missing.
            OSError: If the worker subprocess cannot be started.
        """
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
        logger.info('Started %s process with PID %s', self._handle_name, pid)

    def stop(self) -> None:
        """Stop the running worker subprocess, if one is recorded.

        This method reads the stored PID, sends ``SIGTERM`` to the process,
        and falls back to ``SIGKILL`` if termination fails. If the process is
        already gone or the stored PID is invalid, worker state is cleaned up.

        The stored PID is cleared when the worker is successfully considered
        stopped or no longer present.
        """
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
