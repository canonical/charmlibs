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
import os
import shutil
import subprocess
from dataclasses import asdict

from charmlibs import pathops
from charmlibs.rollingops._models import (
    EtcdConfig,
    RollingOpsEtcdNotConfiguredError,
    RollingOpsFileSystemError,
    with_pebble_retry,
)

BASE_DIR = pathops.LocalPath('/var/lib/rollingops/etcd')
SERVER_CA_PATH = BASE_DIR / 'server-ca.pem'
CONFIG_FILE_PATH = BASE_DIR / 'etcdctl.json'
ETCD_SNAP_NAME = 'charmed-etcd'
ETCDCTL_CMD = f'{ETCD_SNAP_NAME}.etcdctl'


def is_etcdctl_installed() -> bool:
    """Return whether the snap-provided etcdctl command is available."""
    return shutil.which(ETCDCTL_CMD) is not None


def write_trusted_server_ca(tls_ca_pem: str) -> None:
    """Persist the etcd server CA certificate to disk.

    Args:
        tls_ca_pem: PEM-encoded CA certificate.

    Raises:
        PebbleConnectionError: if the remote container cannot be reached
        RollingOpsFileSystemError: if there is a problem when writing the certificates
    """
    try:
        with_pebble_retry(lambda: BASE_DIR.mkdir(parents=True, exist_ok=True))
        with_pebble_retry(lambda: SERVER_CA_PATH.write_text(tls_ca_pem, mode=0o644))
    except (FileNotFoundError, LookupError, NotADirectoryError, PermissionError) as e:
        raise RollingOpsFileSystemError('Failed to persist etcd trusted CA certificate.') from e


def write_config_file(
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
        cacert_path=str(SERVER_CA_PATH),
        cert_path=str(client_cert_path),
        key_path=str(client_key_path),
    )

    try:
        with_pebble_retry(lambda: BASE_DIR.mkdir(parents=True, exist_ok=True))
        with_pebble_retry(
            lambda: CONFIG_FILE_PATH.write_text(json.dumps(asdict(config), indent=2), mode=0o600)
        )
    except (FileNotFoundError, LookupError, NotADirectoryError, PermissionError) as e:
        raise RollingOpsFileSystemError('Failed to persist etcd config file.') from e


def _load_config() -> EtcdConfig:
    """Load etcd configuration from disk.

    Raises:
        RollingOpsEtcdNotConfiguredError: If the config file does not exist.
        RollingOpsFileSystemError: if we faile to read the etcd configuration file or
            file cannot be deserialized.
        PebbleConnectionError: if the remote container cannot be reached
    """
    if not with_pebble_retry(lambda: CONFIG_FILE_PATH.exists()):
        raise RollingOpsEtcdNotConfiguredError(
            f'etcdctl config file does not exist: {CONFIG_FILE_PATH}'
        )

    try:
        data = json.loads(CONFIG_FILE_PATH.read_text())
        return EtcdConfig(**data)
    except FileNotFoundError as e:
        raise RollingOpsEtcdNotConfiguredError('etcd configuration file not found.') from e
    except (IsADirectoryError, PermissionError) as e:
        raise RollingOpsFileSystemError('Failed to read the etcd config file.') from e
    except (json.JSONDecodeError, TypeError) as e:
        raise RollingOpsFileSystemError('Invalid etcd configuration file format.') from e


def load_env() -> dict[str, str]:
    """Return environment variables for etcdctl.

    Returns: A dictionary containing environment variables to pass to subprocess calls.

    Raises:
        RollingOpsEtcdNotConfiguredError: If the environment file does not exist.
        RollingOpsFileSystemError: if we fail to read the etcd configuration file or
            the file cannot be deserialized.
        PebbleConnectionError: if the remote container cannot be reached
    """
    config = _load_config()

    env = os.environ.copy()
    env.update({
        'ETCDCTL_API': '3',
        'ETCDCTL_ENDPOINTS': config.endpoints,
        'ETCDCTL_CACERT': config.cacert_path,
        'ETCDCTL_CERT': config.cert_path,
        'ETCDCTL_KEY': config.key_path,
    })
    return env


def ensure_initialized():
    """Checks whether the etcd config file for etcdctl is setup.

    Raises:
        RollingOpsEtcdNotConfiguredError: if the etcd config file does not exist, etcd
            server CA does not exist or etcdctl is not installed.
        PebbleConnectionError: if the remote container cannot be reached.
    """
    if not with_pebble_retry(lambda: CONFIG_FILE_PATH.exists()):
        raise RollingOpsEtcdNotConfiguredError(
            f'etcdctl config file does not exist: {CONFIG_FILE_PATH}'
        )
    if not with_pebble_retry(lambda: SERVER_CA_PATH.exists()):
        raise RollingOpsEtcdNotConfiguredError(
            f'etcdctl server CA file does not exist: {SERVER_CA_PATH}'
        )
    if not is_etcdctl_installed():
        raise RollingOpsEtcdNotConfiguredError(
            f'etcdctl is not installed. Please install the {ETCD_SNAP_NAME} snap '
            f'to provide {ETCDCTL_CMD}.'
        )


def cleanup() -> None:
    """Removes the etcdctl env file and the trusted etcd server CA.

    Raises:
        RollingOpsFileSystemError: if there is a problem when deleting the files.
        PebbleConnectionError: if the remote container cannot be reached.
    """
    try:
        with_pebble_retry(lambda: SERVER_CA_PATH.unlink(missing_ok=True))
        with_pebble_retry(lambda: CONFIG_FILE_PATH.unlink(missing_ok=True))
    except (IsADirectoryError, PermissionError) as e:
        raise RollingOpsFileSystemError('Failed to remove etcd config file and CA.') from e


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute an etcdctl command.

    Args:
        args: List of arguments to pass to etcdctl.

    Returns:
        A CompletedProcess object containing the result.

    Raises:
        RollingOpsEtcdNotConfiguredError: if the etcd config file does not exist.
        PebbleConnectionError: if the remote container cannot be reached.
        CalledProcessError: if the command execution failed.
        TimeoutExpired: if the command execution timed out.
    """
    ensure_initialized()
    cmd = [ETCDCTL_CMD, *args]
    # TODO: decide where to handle CalledProcessError and TimeoutExpired.
    return subprocess.run(cmd, env=load_env(), check=True, text=True, capture_output=True)
