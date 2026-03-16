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

import argparse
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from sys import version_info
from typing import Any

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateRequestAttributes,
    CertificateSigningRequest,
    PrivateKey,
)
from charmlibs.advanced_rollingops._dp_interfaces_v1 import (
    RequirerCommonModel,
    ResourceCreatedEvent,
    ResourceEndpointsChangedEvent,
    ResourceProviderModel,
    ResourceRequirerEventHandler,
)
from ops import Relation
from ops.charm import (
    CharmBase,
    RelationDepartedEvent,
)
from ops.framework import EventBase, Object

logger = logging.getLogger(__name__)

SECRET_FIELD = "rollingops-client-secret-id"

class RollingOpsNoEtcdRelationError(Exception):
    """Raised if we are trying to process a lock, but do not appear to have a relation yet."""


class RollingOpsEtcdUnreachableError(Exception):
    """Raised if etcd server is unreachable."""


class RollingOpsEtcdNotConfiguredError(Exception):
    """Raised if etcd client has not been configured yet (env file does not exist)."""


def _now_timestamp_str() -> str:
    """UTC timestamp as a string using ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class OperationResult(StrEnum):
    """Callback return values."""

    RELEASE = "release"
    RETRY_RELEASE = "retry-release"
    RETRY_HOLD = "retry-hold"


@dataclass(frozen=True)
class RollingOpsKeys:
    """Collection of etcd key prefixes used for rolling operations.

    Layout:
        /rollingops/{cluster_id}/granted-unit
        /rollingops/{cluster_id}/{owner}/pending/
        /rollingops/{cluster_id}/{owner}/inprogress/
        /rollingops/{cluster_id}/{owner}/completed/

    The distributed lock key is cluster-scoped
    """

    ROOT = "/rollingops"

    cluster_id: str
    owner: str

    @property
    def cluster_prefix(self) -> str:
        """Etcd prefix corresponding to the cluster namespace."""
        return f"{self.ROOT}/{self.cluster_id}/"

    @property
    def _owner_prefix(self) -> str:
        """Etcd prefix for all the queues belonging to an owner."""
        return f"{self.cluster_prefix}{self.owner}"

    @property
    def lock_key(self) -> str:
        """Etcd key of the lock."""
        return f"{self.cluster_prefix}granted-unit"

    @property
    def pending(self) -> str:
        """Prefix for operations waiting to be executed."""
        return f"{self._owner_prefix}/pending/"

    @property
    def inprogress(self) -> str:
        """Prefix for operations currently being executed."""
        return f"{self._owner_prefix}/inprogress/"

    @property
    def completed(self) -> str:
        """Prefix for operations that have finished execution."""
        return f"{self._owner_prefix}/completed/"

    @classmethod
    def for_owner(cls, cluster_id: str, owner: str) -> "RollingOpsKeys":
        """Create a set of keys for a given owner on a cluster."""
        return cls(cluster_id=cluster_id, owner=owner)


class CertificatesManager:
    """Manage generation and persistence of TLS certificates for etcd client access.

    This class is responsible for creating and storing a client Certificate
    Authority (CA) and a client certificate/key pair used to authenticate
    with etcd via TLS. Certificates are generated only once and persisted
    under a local directory so they can be reused across charm executions.

    Certificates are valid for 20 years. They are not renewed or rotated.
    """

    BASE_DIR = Path("/var/lib/rollingops/tls")

    CA_KEY = BASE_DIR / "client-ca.key"
    CA_CERT = BASE_DIR / "client-ca.pem"
    CLIENT_KEY = BASE_DIR / "client.key"
    CLIENT_CERT = BASE_DIR / "client.pem"

    VALIDITY_DAYS = 365 * 20

    @classmethod
    def _exists(cls) -> bool:
        """Check whether the required client certificates already exist.

        Returns:
            True if the client certificate and key are present on disk, otherwise False.
        """
        return cls.CLIENT_KEY.exists() and cls.CLIENT_CERT.exists()

    @classmethod
    def client_paths(cls) -> bool:
        """Return filesystem paths for the client certificate and key.

        Returns:
            A tuple containing:
            - Path to the client certificate
            - Path to the client private key
        """
        return cls.CLIENT_CERT, cls.CLIENT_KEY


    @classmethod
    def persist_client_cert_and_key(cls, cert_pem: str, key_pem: str) -> None:
        """Persist the provided client certificate and key to disk.

        Args:
            cert_pem: PEM-encoded client certificate.
            key_pem: PEM-encoded client private key.
        """
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)
        cls.CLIENT_CERT.write_text(cert_pem)
        cls.CLIENT_KEY.write_text(key_pem)

        os.chmod(cls.CLIENT_CERT, 0o644)
        os.chmod(cls.CLIENT_KEY, 0o600)

    @classmethod
    def has_client_cert_and_key(cls, cert_pem: str, key_pem: str) -> bool:
        """Return whether the provided certificate material matches local files."""
        if not cls.CLIENT_CERT.exists() or not cls.CLIENT_KEY.exists():
            return False

        return cls.CLIENT_CERT.read_text() == cert_pem and cls.CLIENT_KEY.read_text() == key_pem

    @classmethod
    def generate(cls, common_name: str) -> tuple[str, str]:
        """Generate a client CA and client certificate if they do not exist.

        This method creates:
        1. A CA private key and self-signed CA certificate.
        2. A client private key.
        3. A certificate signing request (CSR) using the provided common name.
        4. A client certificate signed by the generated CA.

        The generated files are written to disk and reused in future runs.
        If the certificates already exist, this method does nothing.

        Args:
            common_name: Common Name (CN) used in the client certificate
                subject. This value should not contain slashes.

        Returns:
            A tuple containing:
            - The client certificate PEM string
            - The client private key PEM string
        """
        if cls._exists():
            return cls.CLIENT_CERT.read_text(), cls.CLIENT_KEY.read_text()

        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)

        ca_key = PrivateKey.generate(key_size=4096)
        ca_attributes = CertificateRequestAttributes(
            common_name="rollingops-client-ca", is_ca=True
        )
        ca_crt = Certificate.generate_self_signed_ca(
            attributes=ca_attributes,
            private_key=ca_key,
            validity=timedelta(days=cls.VALIDITY_DAYS),
        )

        client_key = PrivateKey.generate(key_size=4096)

        csr_attributes = CertificateRequestAttributes(
            common_name=common_name, add_unique_id_to_subject_name=False
        )
        csr = CertificateSigningRequest.generate(
            attributes=csr_attributes,
            private_key=client_key,
        )

        client_crt = Certificate.generate(
            csr=csr,
            ca=ca_crt,
            ca_private_key=ca_key,
            validity=timedelta(days=cls.VALIDITY_DAYS),
            is_ca=False,
        )

        cls.CA_KEY.write_text(ca_key.raw)
        cls.CA_CERT.write_text(ca_crt.raw)
        cls.CLIENT_KEY.write_text(client_key.raw)
        cls.CLIENT_CERT.write_text(client_crt.raw)

        os.chmod(cls.CA_KEY, 0o600)
        os.chmod(cls.CLIENT_KEY, 0o600)
        os.chmod(cls.CA_CERT, 0o644)
        os.chmod(cls.CLIENT_CERT, 0o644)

        return client_crt.raw, client_key.raw


class EtcdCtl:
    """Class for interacting with etcd through the etcdctl CLI.

    This class encapsulates configuration and execution of the tool. It manages
    the environment variables required for connecting to an etcd cluster,
    including TLS configuration, and provides convenience methods for
    executing commands and retrieving structured results.
    """

    BASE_DIR = Path("/var/lib/rollingops/etcd")
    SERVER_CA = BASE_DIR / "server-ca.pem"
    ENV_FILE = BASE_DIR / "etcdctl.env"

    @classmethod
    def write_trusted_server_ca(cls, tls_ca_pem: str) -> None:
        """Persist the etcd server CA certificate to disk.

        Args:
            tls_ca_pem: PEM-encoded CA certificate.

        Returns:
            Path to the stored CA certificate.
        """
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)

        cls.SERVER_CA.write_text(tls_ca_pem or "")
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
            client_cert_path:
            client_key_path:
        """
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)

        lines = [
            'export ETCDCTL_API="3"',
            f'export ETCDCTL_ENDPOINTS="{endpoints}"',
            f'export ETCDCTL_CACERT="{cls.SERVER_CA}"',
            f'export ETCDCTL_CERT="{client_cert_path}"',
            f'export ETCDCTL_KEY="{client_key_path}"',
            "",
        ]

        cls.ENV_FILE.write_text("\n".join(lines))
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
            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[len("export ") :].strip()

            if not line.startswith("ETCDCTL_"):
                continue

            key, value = line.split("=", 1)
            env[key] = value.strip().strip('"').strip("'")

        env.setdefault("ETCDCTL_API", "3")
        return env

    @classmethod
    def ensure_initialized(cls):
        """Checks whether the environment file for etcdctl is setup."""
        if not cls.ENV_FILE.exists():
            raise RollingOpsEtcdNotConfiguredError(
                f"etcdctl env file does not exist: {cls.ENV_FILE}"
            )
        if not cls.SERVER_CA.exists():
            raise RollingOpsEtcdNotConfiguredError(
                f"etcdctl server CA file does not exist: {cls.SERVER_CA}"
            )


    @classmethod
    def run(
        cls, args: list[str], check: bool = True, capture: bool = True
    ) -> subprocess.CompletedProcess:
        """Execute an etcdctl command.

        Args:
            args: List of arguments to pass to etcdctl.
            check: If True, raise an exception on non-zero exit status.
            capture: Whether to capture stdout and stderr.

        Returns:
            A CompletedProcess object containing the result.
        """
        cls.ensure_initialized()
        cmd = ["etcdctl", *args]
        return subprocess.run(
            cmd, env=cls.load_env(), check=check, text=True, capture_output=capture
        )

    @classmethod
    def get_first_key_value(cls, key_prefix: str) -> tuple[str, dict] | None:
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
            ["get", key_prefix, "--prefix", "--limit=1"],
            check=False,
        )

        if res.returncode != 0:
            return None

        out = res.stdout.strip().splitlines()
        if len(out) < 2:
            return None

        return out[0], json.loads(out[1])

    @classmethod
    def get_last_key_value(cls, key_prefix: str) -> tuple[str, dict] | None:
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
            ["get", key_prefix, "--prefix", "--sort-by=KEY", "--order=DESCEND", "--limit=1"],
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
            ["bash", "-lc", f"printf %s '{txn}' | etcdctl txn"],
            text=True,
            env=cls.load_env(),
            capture_output=True,
            check=False,
        )

        logger.debug("etcd txn result: %s", res.stdout)
        return "SUCCESS" in res.stdout

class SharedClientCertificateManager(Object):
    """Manage the shared rollingops client certificate via peer relation secret."""

    def __init__(self, charm, peer_relation_name: str) -> None:
        super().__init__(charm, "shared-client-certificate")
        self.charm = charm
        self.peer_relation_name = peer_relation_name

        self.framework.observe(charm.on.leader_elected, self._on_leader_elected)
        self.framework.observe(
            charm.on[peer_relation_name].relation_changed,
            self._on_peer_relation_changed,
        )
        self.framework.observe(charm.on.secret_changed, self._on_secret_changed)

    @property
    def _peer_relation(self) -> Relation | None:
        return self.model.get_relation(self.peer_relation_name)

    def _on_leader_elected(self, event) -> None:
        self.create_and_share_certificate()

    def _on_secret_changed(self, event):
        # if event.secret.label == "rollingops-client-cert":
        #    self._sync_client_certificate()
        self.sync_to_local_files()

    def _on_peer_relation_changed(self, event) -> None:
        """React to peer relation changes.

        The leader ensures the shared certificate exists.
        All units try to persist the shared certificate locally if available.
        """
        self.create_and_share_certificate()
        self.sync_to_local_files()

    def create_and_share_certificate(self) -> None:
        """Ensure the application client certificate exists.

        Only the leader generates the certificate and writes it to the peer
        relation application databag.
        """
        relation = self._peer_relation
        if relation is None or not self.model.unit.is_leader():
            return

        app_data = relation.data[self.model.app]
        secret_id = app_data.get(SECRET_FIELD)
        if secret_id:
            return

        common_name = f"rollingops-{self.model.uuid}-{self.model.app.name}"
        cert_pem, key_pem = CertificatesManager.generate(common_name)

        secret = self.model.app.add_secret({"cert": cert_pem, "key": key_pem})
        app_data[SECRET_FIELD] = secret.id

    def get_shared_certificate(self) -> tuple[str, str] | None:
        """Return the client certificate and key from peer app data.

        Returns:
            A tuple of (certificate_pem, key_pem), or None if not yet available.
        """
        relation = self._peer_relation
        if relation is None:
            return None

        secret_id = relation.data[self.model.app].get(SECRET_FIELD)
        if not secret_id:
            return None

        secret = self.model.get_secret(id=secret_id)
        content = secret.get_content(refresh=True)
        return content["cert"], content["key"]

    def sync_to_local_files(self) -> None:
        """Persist shared certificate locally if available."""
        shared = self.get_shared_certificate()
        if shared is None:
            logger.debug("Shared rollingops client certificate is not available yet")
            return False

        cert_pem, key_pem = shared
        if CertificatesManager.has_client_cert_and_key(cert_pem, key_pem):
            return

        CertificatesManager.persist_client_cert_and_key(cert_pem, key_pem)


    def get_local_request_cert(self) -> str:
        """Return the cert to place in relation requests."""
        shared = self.get_shared_certificate()
        return "" if shared is None else shared[0]

class EtcdRequiresV1(Object):
    """EtcdRequires implementation for data interfaces version 1."""

    def __init__(
        self,
        charm,
        relation_name: str,
        cluster_id: str,
        shared_certificates: SharedClientCertificateManager,
    ) -> None:
        super().__init__(charm, "requirer-etcd")
        self.charm = charm
        self.cluster_id = cluster_id
        self.shared_certificates = shared_certificates

        self.etcd_interface = ResourceRequirerEventHandler(
            self.charm,
            relation_name=relation_name,
            requests=self.client_requests(),
            response_model=ResourceProviderModel,
        )

        self.framework.observe(
            self.etcd_interface.on.endpoints_changed, self._on_endpoints_changed
        )
        self.framework.observe(self.etcd_interface.on.resource_created, self._on_resource_created)

    @property
    def etcd_relation(self) -> Relation | None:
        """Return the etcd relation if present."""
        relations = self.etcd_interface.relations
        return relations[0] if relations else None

    def _on_endpoints_changed(
        self, event: ResourceEndpointsChangedEvent[ResourceProviderModel]
    ) -> None:
        """Handle etcd client relation data changed event."""
        response = event.response
        logger.info("etcd endpoints changed: %s", response.endpoints)

        if not response.endpoints:
            logger.error("No etcd endpoints available")
            return

        self.shared_certificates.sync_to_local_files()
        cert_path, key_path = CertificatesManager.client_paths()
        EtcdCtl.write_env_file(
            endpoints=response.endpoints,
            client_cert_path=cert_path,
            client_key_path=key_path,
        )

    def _on_resource_created(self, event: ResourceCreatedEvent[ResourceProviderModel]) -> None:
        """Handle resource created event."""
        response = event.response

        if not response.tls_ca:
            logger.error("No etcd server CA chain available")
            return

        EtcdCtl.write_trusted_server_ca(tls_ca_pem=response.tls_ca)

        if response.endpoints:
            cert_path, key_path = CertificatesManager.client_paths()
            EtcdCtl.write_env_file(endpoints=response.endpoints,client_cert_path=cert_path,client_key_path=key_path)
        else:
            logger.error("No etcd endpoints available")

        self.shared_certificates.sync_to_local_files()

    def client_requests(self) -> list[RequirerCommonModel]:
        """Return the client requests for the etcd requirer interface."""
        return [
            RequirerCommonModel(
                resource=self.cluster_id,
                mtls_cert=self.shared_certificates.get_local_request_cert(),
            )
        ]


class RollingOpsLockGrantedEvent(EventBase):
    """Custom event emitted when the background worker grants the lock."""


class EtcdRollingOpsManager(Object):
    """Rolling ops manager for clusters."""

    def __init__(
        self,
        charm: CharmBase,
        peer_relation_name: str,
        etcd_relation_name: str,
        cluster_id: str,
        callback_targets: dict[str, Any],
    ):
        """Register our custom events.

        params:
            charm: the charm we are attaching this to.
            peer_relation_name: peer relation used for rolling ops.
            etcd_relation_name: the relation to integrate with etcd.
            cluster_id: unique identifier for the cluster
            callback_targets: mapping from callback_id -> callable.
        """
        super().__init__(charm, "rolling-ops-manager")
        self._charm = charm
        self.peer_relation_name = peer_relation_name
        self.etcd_relation_name = etcd_relation_name
        self.callback_targets = callback_targets
        self.charm_dir = charm.charm_dir

        owner = f"{self.model.uuid}-{self.model.unit.name}".replace("/", "-")
        self.worker = EtcdRollingOpsAsyncWorker(
            charm, peer_relation_name=peer_relation_name, owner=owner
        )
        self.keys = RollingOpsKeys.for_owner(cluster_id, owner)

        self.shared_certificates = SharedClientCertificateManager(
            charm,
            peer_relation_name=peer_relation_name,
        )

        self.etcd = EtcdRequiresV1(
            charm,
            relation_name=etcd_relation_name,
            cluster_id=self.keys.cluster_prefix,
            shared_certificates=self.shared_certificates,
        )

        charm.on.define_event("rollingops_lock_granted", RollingOpsLockGrantedEvent)

        self.framework.observe(
            charm.on[self.peer_relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(
            charm.on[self.etcd_relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(charm.on.rollingops_lock_granted, self._on_rollingop_granted)
        self.framework.observe(charm.on.install, self._on_install)


    @property
    def _peer_relation(self) -> Relation | None:
        return self.model.get_relation(self.peer_relation_name)

    @property
    def _etcd_relation(self) -> Relation | None:
        return self.model.get_relation(self.etcd_relation_name)

    def _on_install(self, event) -> None:
        subprocess.run(["apt-get", "update"], check=True)
        subprocess.run(["apt-get", "install", "-y", "etcd-client"], check=True)


    def _on_rollingop_granted(self, event: RollingOpsLockGrantedEvent) -> None:
        if not self._peer_relation or not self._etcd_relation:
            return
        try:
            EtcdCtl.ensure_initialized()
        except RollingOpsEtcdNotConfiguredError:
            return
        logger.info("Received a rolling-op lock granted event.")
        self._on_run_with_lock()

    def _on_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Leader cleanup: if a departing unit was granted, clear the grant.

        This prevents deadlocks when the granted unit leaves the relation.
        """
        unit = event.departing_unit
        if unit == self.model.unit:
            self.worker.stop()

    def request_async_lock(
        self,
        callback_id: str,
        kwargs: dict[str, Any] | None = None,
        max_retry: int | None = None,
    ) -> None:
        """Queue a rolling operation and trigger asynchronous lock acquisition.

        This method creates a new operation representing a callback to execute
        once the distributed lock is granted. The operation is appended to the
        unit's pending operation queue stored in etcd.

        If the operation is successfully enqueued, the background worker process
        responsible for acquiring the distributed lock and processing operations
        is started.

        Args:
            callback_id: Identifier of the registered callback to execute when
                the lock is granted.
            kwargs: Optional keyword arguments passed to the callback when
                executed. Must be JSON-serializable.
            max_retry: Maximum number of retries for the operation.
                - None: retry indefinitely
                - 0: do not retry on failure

        Raises:
            ValueError: If the callback_id is not registered or invalid parameters
            RollingOpsNoEtcdRelationError: if the etcd relation does not exist
            RollingOpsEtcdNotConfiguredError: if etcd client has not been configured yet
        """
        if callback_id not in self.callback_targets:
            raise ValueError(f"Unknown callback_id: {callback_id}")

        etcd_relation = self.model.get_relation(self.etcd_relation_name)
        if not etcd_relation:
            raise RollingOpsNoEtcdRelationError

        EtcdCtl.ensure_initialized()

        self.worker.start()

    def _on_run_with_lock(self) -> None:
        """Execute the current operation while holding the distributed lock.

        This method is triggered when the worker determines that the current
        unit owns the distributed lock. The method retrieves the head operation
        from the in-progress queue and executes its registered callback.

        After execution, the operation is moved to the completed queue and its
        updated state is persisted.
        """
        EtcdCtl.run(["put", self.keys.lock_key, self.keys.owner])

        proc = EtcdCtl.run(["get", self.keys.lock_key, "--print-value-only"], check=False)

        if proc.returncode != 0:
            return False

        value = proc.stdout.strip()
        if value != self.keys.owner:
            logger.info("Callback not executed.")

        callback = self.callback_targets.get("_restart", "")
        callback(delay=1)


class EtcdRollingOpsAsyncWorker(Object):
    """Spawns and manages the external rolling-ops worker process."""

    def __init__(self, charm: CharmBase, peer_relation_name: str, owner: str):
        super().__init__(charm, "etcd-ollingops-async-worker")
        self._charm = charm
        self._peer_relation_name = peer_relation_name
        self._run_cmd = "/usr/bin/juju-exec"
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

        pid_str = self._unit_data.get("etcd-rollingops-worker-pid", "")
        if pid_str:
            try:
                pid = int(pid_str)
            except ValueError:
                pid = -1

            if self._is_pid_alive(pid):
                logger.info(
                    "RollingOps worker already running with PID %s; not starting a new one.", pid
                )
                return

        # Remove JUJU_CONTEXT_ID so juju-run works from the spawned process
        new_env = os.environ.copy()
        new_env.pop("JUJU_CONTEXT_ID", None)

        for loc in new_env.get("PYTHONPATH", "").split(":"):
            path = Path(loc)
            venv_path = (
                path
                / ".."
                / "venv"
                / "lib"
                / f"python{version_info.major}.{version_info.minor}"
                / "site-packages"
            )
            if path.stem == "lib":
                new_env["PYTHONPATH"] = f"{venv_path.resolve()}:{new_env['PYTHONPATH']}"
                break

        worker = self._charm_dir / "lib/charms/rolling_ops/v1" / "rollingops.py"

        pid = subprocess.Popen(
            [
                "/usr/bin/python3",
                "-u",
                str(worker),
                "--run-cmd",
                self._run_cmd,
                "--unit-name",
                self.model.unit.name,
                "--charm-dir",
                str(self._charm_dir),
                "--owner",
                self._owner,
            ],
            cwd=str(self._charm_dir),
            stdout=open("/var/log/etcd_rollingops_worker.log", "a"),
            stderr=open("/var/log/etcd_rollingops_worker.err", "a"),
            env=new_env,
        ).pid

        self._unit_data.update({"etcd-rollingops-worker-pid": str(pid)})
        logger.info("Started etcd rollingops worker process with PID %s", pid)

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
        pid_str = self._unit_data.get("etcd-rollingops-worker-pid", "")
        if not pid_str:
            return

        pid = int(pid_str)
        try:
            os.kill(pid, signal.SIGINT)
            logger.info("Stopped etcd rollingops worker process PID %s", pid)
        except OSError:
            logger.info("Failed to stop etcd rollingops worker process PID %s", pid)
            pass
        self._unit_data.update({"etcd-rollingops-worker-pid": ""})


def main():
    """Juju hook event dispatcher."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-cmd", required=True)
    parser.add_argument("--unit-name", required=True)
    parser.add_argument("--charm-dir", required=True)
    parser.add_argument("--owner", required=True)
    args = parser.parse_args()

    time.sleep(10)

    dispatch_sub_cmd = (
        f"JUJU_DISPATCH_PATH=hooks/rollingops_lock_granted {args.charm_dir}/dispatch"
    )
    res = subprocess.run([args.run_cmd, "-u", args.unit_name, dispatch_sub_cmd])
    res.check_returncode()


if __name__ == "__main__":
    main()
