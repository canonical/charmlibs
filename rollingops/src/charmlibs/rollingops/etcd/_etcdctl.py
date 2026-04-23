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

"""Functions for interacting with etcd through the etcdctl CLI.

The functions in this file manage the environment variables required for
connecting to an etcd cluster, including TLS configuration, and provide
convenience functions for executing commands and retrieving structured results.
"""

import json
import logging
import os
import shutil
import subprocess
from dataclasses import asdict

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from charmlibs import pathops
from charmlibs.rollingops.common._exceptions import (
    RollingOpsEtcdctlFatalError,
    RollingOpsEtcdctlParseError,
    RollingOpsEtcdctlRetryableError,
    RollingOpsEtcdNotConfiguredError,
    RollingOpsFileSystemError,
)
from charmlibs.rollingops.common._utils import with_pebble_retry
from charmlibs.rollingops.etcd._models import CERT_MODE, EtcdConfig, EtcdKV

logger = logging.getLogger(__name__)

ETCDCTL_CMD = 'etcdctl'
ETCDCTL_TIMEOUT_SECONDS = 15
ETCDCTL_RETRY_ATTEMPTS = 12
ETCDCTL_RETRY_WAIT_SECONDS = 5


class Etcdctl:
    def __init__(self, base_dir: str):
        self.base_dir = pathops.LocalPath(base_dir) / 'etcd'
        self.server_ca_path = self.base_dir / 'server-ca.pem'
        self.config_file_path = self.base_dir / 'etcdctl.json'

    def is_etcdctl_installed(self) -> bool:
        """Return whether the snap-provided etcdctl command is available."""
        return shutil.which(ETCDCTL_CMD) is not None

    def write_trusted_server_ca(self, tls_ca_pem: str) -> None:
        """Persist the etcd server CA certificate to disk.

        Args:
            tls_ca_pem: PEM-encoded CA certificate.

        Raises:
            PebbleConnectionError: if the remote container cannot be reached
            RollingOpsFileSystemError: if there is a problem when writing the certificates
        """
        try:
            with_pebble_retry(lambda: self.base_dir.mkdir(parents=True, exist_ok=True))
            with_pebble_retry(lambda: self.server_ca_path.write_text(tls_ca_pem, mode=CERT_MODE))
        except (FileNotFoundError, LookupError, NotADirectoryError, PermissionError) as e:
            raise RollingOpsFileSystemError(
                'Failed to persist etcd trusted CA certificate.'
            ) from e

    def write_config_file(
        self,
        endpoints: str,
        client_cert_path: pathops.LocalPath,
        client_key_path: pathops.LocalPath,
    ) -> None:
        """Create or update the etcdctl configuration JSON file.

        This function writes a JSON file containing the required ETCDCTL_*
        variables used by etcdctl to connect to the etcd cluster.

        Args:
            endpoints: Comma-separated list of etcd endpoints.
            client_cert_path: Path to the client certificate.
            client_key_path: Path to the client private key.

        Raises:
            PebbleConnectionError: if the remote container cannot be reached
            RollingOpsFileSystemError: if there is a problem when writing the certificates
        """
        config = EtcdConfig(
            endpoints=endpoints,
            cacert_path=str(self.server_ca_path),
            cert_path=str(client_cert_path),
            key_path=str(client_key_path),
        )

        try:
            with_pebble_retry(lambda: self.base_dir.mkdir(parents=True, exist_ok=True))
            with_pebble_retry(
                lambda: self.config_file_path.write_text(
                    json.dumps(asdict(config), indent=2), mode=0o600
                )
            )
        except (FileNotFoundError, LookupError, NotADirectoryError, PermissionError) as e:
            raise RollingOpsFileSystemError('Failed to persist etcd config file.') from e

    def _load_config(self) -> EtcdConfig:
        """Load etcd configuration from disk.

        Raises:
            RollingOpsEtcdNotConfiguredError: If the config file does not exist.
            RollingOpsFileSystemError: if we faile to read the etcd configuration file or
                file cannot be deserialized.
            PebbleConnectionError: if the remote container cannot be reached
        """
        if not with_pebble_retry(lambda: self.config_file_path.exists()):
            raise RollingOpsEtcdNotConfiguredError(
                f'etcdctl config file does not exist: {self.config_file_path}'
            )

        try:
            data = json.loads(self.config_file_path.read_text())
            return EtcdConfig(**data)
        except FileNotFoundError as e:
            raise RollingOpsEtcdNotConfiguredError('etcd configuration file not found.') from e
        except (IsADirectoryError, PermissionError) as e:
            raise RollingOpsFileSystemError('Failed to read the etcd config file.') from e
        except (json.JSONDecodeError, TypeError) as e:
            raise RollingOpsFileSystemError('Invalid etcd configuration file format.') from e

    def load_env(self) -> dict[str, str]:
        """Return environment variables for etcdctl.

        Returns: A dictionary containing environment variables to pass to subprocess calls.

        Raises:
            RollingOpsEtcdNotConfiguredError: If the environment file does not exist.
            RollingOpsFileSystemError: if we fail to read the etcd configuration file or
                the file cannot be deserialized.
            PebbleConnectionError: if the remote container cannot be reached
        """
        config = self._load_config()

        env = os.environ.copy()
        env.update({
            'ETCDCTL_API': '3',
            'ETCDCTL_ENDPOINTS': config.endpoints,
            'ETCDCTL_CACERT': config.cacert_path,
            'ETCDCTL_CERT': config.cert_path,
            'ETCDCTL_KEY': config.key_path,
        })
        return env

    def ensure_initialized(self):
        """Checks whether the etcd config file for etcdctl is setup.

        Raises:
            RollingOpsEtcdNotConfiguredError: if the etcd config file does not exist, etcd
                server CA does not exist or etcdctl is not installed.
            PebbleConnectionError: if the remote container cannot be reached.
        """
        if not with_pebble_retry(lambda: self.config_file_path.exists()):
            raise RollingOpsEtcdNotConfiguredError(
                f'etcdctl config file does not exist: {self.config_file_path}'
            )
        if not with_pebble_retry(lambda: self.server_ca_path.exists()):
            raise RollingOpsEtcdNotConfiguredError(
                f'etcdctl server CA file does not exist: {self.server_ca_path}'
            )
        if not self.is_etcdctl_installed():
            raise RollingOpsEtcdNotConfiguredError(f'{ETCDCTL_CMD} is not installed.')

    def cleanup(self) -> None:
        """Removes the etcdctl env file and the trusted etcd server CA.

        Raises:
            RollingOpsFileSystemError: if there is a problem when deleting the files.
            PebbleConnectionError: if the remote container cannot be reached.
        """
        try:
            with_pebble_retry(lambda: self.server_ca_path.unlink(missing_ok=True))
            with_pebble_retry(lambda: self.config_file_path.unlink(missing_ok=True))
        except (IsADirectoryError, PermissionError) as e:
            raise RollingOpsFileSystemError('Failed to remove etcd config file and CA.') from e

    def _is_retryable_stderr(self, stderr: str) -> bool:
        """Return whether stderr looks like a transient etcd/client failure."""
        text = stderr.lower()
        retryable_markers = (
            'connection refused',
            'context deadline exceeded',
            'deadline exceeded',
            'temporarily unavailable',
            'transport is closing',
            'connection reset',
            'broken pipe',
            'unavailable',
            'leader changed',
            'etcdserver: request timed out',
        )
        return any(marker in text for marker in retryable_markers)

    @retry(
        retry=retry_if_exception_type(RollingOpsEtcdctlRetryableError),
        stop=stop_after_attempt(ETCDCTL_RETRY_ATTEMPTS),
        wait=wait_fixed(ETCDCTL_RETRY_WAIT_SECONDS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _run_checked(
        self, *args: str, cmd_input: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Execute etcdctl and return the completed process.

        Raises:
            RollingOpsEtcdNotConfiguredError: if etcdctl is not configured.
            PebbleConnectionError: if the remote container cannot be reached.
            RollingOpsEtcdctlRetryableError: for transient command failures.
            RollingOpsEtcdctlFatalError: for non-retryable command failures.
        """
        self.ensure_initialized()

        cmd = [ETCDCTL_CMD, *args]

        try:
            res = subprocess.run(
                cmd,
                env=self.load_env(),
                input=cmd_input,
                text=True,
                capture_output=True,
                check=False,
                timeout=ETCDCTL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            logger.warning(
                'Timed out running etcdctl: cmd=%r stdout=%r stderr=%r', cmd, e.stdout, e.stderr
            )
            raise RollingOpsEtcdctlRetryableError(f'Timed out running etcdctl: {cmd!r}') from e
        except FileNotFoundError as e:
            logger.exception('etcdctl executable not found: %s', ETCDCTL_CMD)
            raise RollingOpsEtcdctlFatalError(
                f'etcdctl executable not found: {ETCDCTL_CMD}'
            ) from e
        except OSError as e:
            logger.exception('Failed to execute etcdctl: cmd=%r', cmd)
            raise RollingOpsEtcdctlFatalError(f'Failed to execute etcdctl: {cmd!r}') from e

        if res.returncode != 0:
            logger.warning(
                'etcdctl command failed: cmd=%r returncode=%s stdout=%r stderr=%r',
                cmd,
                res.returncode,
                res.stdout,
                res.stderr,
            )
            if self._is_retryable_stderr(res.stderr):
                raise RollingOpsEtcdctlRetryableError(
                    f'Retryable etcdctl failure (rc={res.returncode}): {res.stderr.strip()}'
                )
            raise RollingOpsEtcdctlFatalError(
                f'etcdctl failed (rc={res.returncode}): {res.stderr.strip()}'
            )

        logger.debug('etcdctl command succeeded: cmd=%r stdout=%r', cmd, res.stdout)
        return res

    def run(self, *args: str, cmd_input: str | None = None) -> str:
        """Execute an etcdctl command.

        Args:
            args: List of arguments to pass to etcdctl.
            cmd_input: value to use as input when running the command.

        Returns:
            The stdout of the command, stripped, or None if execution failed.

        Raises:
            RollingOpsEtcdNotConfiguredError: if etcdctl is not configured.
            RollingOpsFileSystemError: if configuration cannot be read.
            PebbleConnectionError: if the remote container cannot be reached.
            RollingOpsEtcdctlError: etcdctl command error.
        """
        return self._run_checked(*args, cmd_input=cmd_input).stdout.strip()

    def _get_key_value_pair(self, key_prefix: str, *extra_args: str) -> EtcdKV | None:
        """Retrieve the first key and value under a given prefix.

        Args:
            key_prefix: Key prefix to search for.
            extra_args: Arguments to the get command

        Returns:
            A EtcdKV containing:
            - The key string
            - The parsed JSON value as a dictionary

            Returns None if no key exists.

        Raises:
            RollingOpsEtcdctlParseError: if the output is malformed

        """
        res = self.run('get', key_prefix, '--prefix', *extra_args)
        out = res.splitlines()
        if len(out) < 2:
            return None

        try:
            value = json.loads(out[1])
        except json.JSONDecodeError as e:
            raise RollingOpsEtcdctlParseError(
                f'Failed to parse JSON value for key {out[0]}: {out[1]}'
            ) from e

        return EtcdKV(key=out[0], value=value)

    def get_first_key_value_pair(self, key_prefix: str) -> EtcdKV | None:
        """Retrieve the first key and value under a given prefix.

        Args:
            key_prefix: Key prefix to search for.

        Returns:
            A tuple containing:
            - The key string
            - The parsed JSON value as a dictionary

            Returns None if no key exists or the command fails.

        Raises:
            RollingOpsEtcdctlParseError: if the output is malformed
        """
        return self._get_key_value_pair(key_prefix, '--limit=1')

    def get_last_key_value_pair(self, key_prefix: str) -> EtcdKV | None:
        """Retrieve the last key and value under a given prefix.

        Args:
            key_prefix: Key prefix to search for.

        Returns:
            A tuple containing:
            - The key string
            - The parsed JSON value as a dictionary

            Returns None if no key exists or the command fails.

        Raises:
            RollingOpsEtcdctlParseError: if the output is malformed
        """
        return self._get_key_value_pair(
            key_prefix,
            '--sort-by=KEY',
            '--order=DESCEND',
            '--limit=1',
        )

    def txn(self, txn_input: str) -> bool:
        """Execute an etcd transaction.

        The transaction string should follow the etcdctl transaction format
        where comparison statements are followed by operations.

        Args:
            txn_input: The transaction specification passed to `etcdctl txn`.

        Returns:
            True if the transaction succeeded, otherwise False.

        Raises:
            RollingOpsEtcdNotConfiguredError: if etcdctl is not configured.
            PebbleConnectionError: if the remote container cannot be reached.
            RollingOpsEtcdctlError: etcdctl command error.
            RollingOpsEtcdctlParseError: if invalid response is found
        """
        res = self._run_checked('txn', cmd_input=txn_input)

        lines = res.stdout.splitlines()
        if not lines:
            raise RollingOpsEtcdctlParseError('Empty txn response')

        first_line = lines[0].strip()

        if first_line == 'SUCCESS':
            return True
        if first_line == 'FAILURE':
            return False

        raise RollingOpsEtcdctlParseError(f'Unexpected txn response: {res.stdout}')
