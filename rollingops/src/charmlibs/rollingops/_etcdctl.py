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

import json
import logging
import os
import subprocess
from pathlib import Path

from charmlibs.rollingops._models import RollingOpsEtcdNotConfiguredError

logger = logging.getLogger(__name__)


class EtcdCtl:
    """Class for interacting with etcd through the etcdctl CLI.

    This class encapsulates configuration and execution of the tool. It manages
    the environment variables required for connecting to an etcd cluster,
    including TLS configuration, and provides convenience methods for
    executing commands and retrieving structured results.
    """

    BASE_DIR = Path('/var/lib/rollingops/etcd')
    SERVER_CA = BASE_DIR / 'server-ca.pem'
    ENV_FILE = BASE_DIR / 'etcdctl.env'

    @classmethod
    def write_trusted_server_ca(cls, tls_ca_pem: str) -> None:
        """Persist the etcd server CA certificate to disk.

        Args:
            tls_ca_pem: PEM-encoded CA certificate.

        Returns:
            Path to the stored CA certificate.
        """
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)

        cls.SERVER_CA.write_text(tls_ca_pem or '')
        os.chmod(cls.SERVER_CA, 0o644)

    @classmethod
    def write_env_file(
        cls,
        endpoints: str,
        client_cert_path: Path,
        client_key_path: Path,
    ) -> None:
        """Create or update the etcdctl environment configuration file.

        This method writes an environment file containing the required
        ETCDCTL_* variables used by etcdctl to connect to the etcd cluster.

        Args:
            endpoints: Comma-separated list of etcd endpoints.
            client_cert_path: Path to the client certificate.
            client_key_path: Path to the client private key.
        """
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)

        lines = [
            'export ETCDCTL_API="3"',
            f'export ETCDCTL_ENDPOINTS="{endpoints}"',
            f'export ETCDCTL_CACERT="{cls.SERVER_CA}"',
            f'export ETCDCTL_CERT="{client_cert_path}"',
            f'export ETCDCTL_KEY="{client_key_path}"',
            '',
        ]

        cls.ENV_FILE.write_text('\n'.join(lines))
        os.chmod(cls.ENV_FILE, 0o600)

    @classmethod
    def load_env(cls) -> dict[str, str]:
        """Load etcdctl environment variables from the env file.

        Parses the generated environment file and extracts ETCDCTL_*
        variables so they can be injected into subprocess environments.

        Returns:
            A dictionary containing environment variables to pass to
            subprocess calls.

        Raises:
            RollingOpsEtcdNotConfiguredError: If the environment file does not exist.
        """
        cls.ensure_initialized()

        env = os.environ.copy()

        for line in cls.ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if line.startswith('export '):
                line = line[len('export ') :].strip()

            if not line.startswith('ETCDCTL_'):
                continue

            key, value = line.split('=', 1)
            env[key] = value.strip().strip('"').strip("'")

        env.setdefault('ETCDCTL_API', '3')
        return env

    @classmethod
    def ensure_initialized(cls):
        """Checks whether the environment file for etcdctl is setup."""
        if not cls.ENV_FILE.exists():
            raise RollingOpsEtcdNotConfiguredError(
                f'etcdctl env file does not exist: {cls.ENV_FILE}'
            )
        if not cls.SERVER_CA.exists():
            raise RollingOpsEtcdNotConfiguredError(
                f'etcdctl server CA file does not exist: {cls.SERVER_CA}'
            )

    @classmethod
    def cleanup(cls) -> None:
        """Removes the etcdctl env file and the trusted etcd server CA."""
        cls.SERVER_CA.unlink(missing_ok=True)
        cls.ENV_FILE.unlink(missing_ok=True)

    @classmethod
    def run(
        cls, args: list[str], check: bool = True, capture: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Execute an etcdctl command.

        Args:
            args: List of arguments to pass to etcdctl.
            check: If True, raise an exception on non-zero exit status.
            capture: Whether to capture stdout and stderr.

        Returns:
            A CompletedProcess object containing the result.
        """
        cls.ensure_initialized()
        cmd = ['etcdctl', *args]
        return subprocess.run(
            cmd, env=cls.load_env(), check=check, text=True, capture_output=capture
        )

    @classmethod
    def get_first_key_value(cls, key_prefix: str) -> tuple[str, dict[str, str]] | None:
        """Retrieve the first key and value under a given prefix.

        Args:
            key_prefix: Key prefix to search for.

        Returns:
            A tuple containing:
            - The key string
            - The parsed JSON value as a dictionary

            Returns None if no key exists or the command fails.
        """
        res = cls.run(
            ['get', key_prefix, '--prefix', '--limit=1'],
            check=False,
        )

        if res.returncode != 0:
            return None

        out = res.stdout.strip().splitlines()
        if len(out) < 2:
            return None

        return out[0], json.loads(out[1])

    @classmethod
    def get_last_key_value(cls, key_prefix: str) -> tuple[str, dict[str, str]] | None:
        """Retrieve the last key and value under a given prefix.

        Args:
            key_prefix: Key prefix to search for.

        Returns:
            A tuple containing:
            - The key string
            - The parsed JSON value as a dictionary

            Returns None if no key exists or the command fails.
        """
        res = cls.run(
            ['get', key_prefix, '--prefix', '--sort-by=KEY', '--order=DESCEND', '--limit=1'],
            check=False,
        )
        if res.returncode != 0:
            return None
        out = res.stdout.strip().splitlines()
        if len(out) < 2:
            return None

        return out[0], json.loads(out[1])

    @classmethod
    def txn(cls, txn: str) -> bool:
        """Execute an etcd transaction.

        The transaction string should follow the etcdctl transaction format
        where comparison statements are followed by operations.

        Args:
            txn: The transaction specification passed to `etcdctl txn`.

        Returns:
            True if the transaction succeeded, otherwise False.
        """
        cls.ensure_initialized()
        res = subprocess.run(
            ['bash', '-lc', f"printf %s '{txn}' | etcdctl txn"],
            text=True,
            env=cls.load_env(),
            capture_output=True,
            check=False,
        )

        logger.debug('etcd txn result: %s', res.stdout)
        return 'SUCCESS' in res.stdout
