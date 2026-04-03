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

"""etcd rolling ops models."""

from dataclasses import dataclass
from typing import ClassVar

from charmlibs.interfaces.tls_certificates import Certificate, PrivateKey
from charmlibs.pathops import LocalPath
from charmlibs.rollingops.common._models import (
    with_pebble_retry,
)

CERT_MODE = 0o644
KEY_MODE = 0o600


@dataclass(frozen=True)
class SharedCertificate:
    """Represent the certificates shared within units of an app to connect to etcd."""

    certificate: Certificate
    key: PrivateKey
    ca: Certificate

    @classmethod
    def from_paths(
        cls, cert_path: LocalPath, key_path: LocalPath, ca_path: LocalPath
    ) -> 'SharedCertificate':
        """Create a SharedCertificate from certificate files on disk.

        This method reads the certificate, private key, and CA certificate
        from the provided file paths and converts them into their respective
        typed objects.

        Args:
            cert_path: Path to the client certificate file (PEM format).
            key_path: Path to the private key file (PEM format).
            ca_path: Path to the CA certificate file (PEM format).

        Returns:
            A SharedCertificate instance containing the loaded certificate material.

        Raises:
            TLSCertificatesError: If any certificate cannot be parsed.
            ValueError: If the key cannot be parsed
            PebbleConnectionError: If the remote container cannot be reached
                after retries.
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be accessed.
        """
        return cls(
            certificate=Certificate.from_string(cls._read_text_with_retry(cert_path)),
            key=PrivateKey.from_string(cls._read_text_with_retry(key_path)),
            ca=Certificate.from_string(cls._read_text_with_retry(ca_path)),
        )

    @classmethod
    def from_strings(cls, certificate: str, key: str, ca: str) -> 'SharedCertificate':
        """Create a SharedCertificate from PEM-encoded strings.

        Raises:
            TLSCertificatesError: If any certificate cannot be parsed.
            ValueError: If the key cannot be parsed
        """
        return cls(
            certificate=Certificate.from_string(certificate),
            key=PrivateKey.from_string(key),
            ca=Certificate.from_string(ca),
        )

    def write_to_paths(
        self, cert_path: LocalPath, key_path: LocalPath, ca_path: LocalPath
    ) -> None:
        """Write the certificate material to disk.

        This method writes the client certificate, private key, and CA certificate
        to the specified file paths using appropriate file permissions.

        - Certificate and CA files are written with mode 0o644.
        - Private key is written with mode 0o600.

        Args:
            cert_path: Path where the client certificate will be written.
            key_path: Path where the private key will be written.
            ca_path: Path where the CA certificate will be written.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached
                after retries.
            PermissionError: If the file cannot be written.
            NotADirectoryError: If the parent path is invalid.
        """
        self._write_text_with_retry(path=cert_path, content=self.certificate.raw, mode=CERT_MODE)
        self._write_text_with_retry(path=key_path, content=self.key.raw, mode=KEY_MODE)
        self._write_text_with_retry(path=ca_path, content=self.ca.raw, mode=CERT_MODE)

    @classmethod
    def _read_text_with_retry(cls, path: LocalPath) -> str:
        """Read the content of a file, retrying on transient Pebble errors.

        Args:
            path: The file path to read.

        Returns:
            The file content as a string.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached
                after retries.
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be accessed.
        """
        return with_pebble_retry(lambda: path.read_text())

    def _write_text_with_retry(self, path: LocalPath, content: str, mode: int) -> None:
        """Write text to a file, retrying on transient Pebble errors.

        Args:
            path: The file path to write to.
            content: The text content to write.
            mode: File permission mode to apply (e.g. 0o600).

        Raises:
            PebbleConnectionError: If the remote container cannot be reached
                after retries.
            PermissionError: If the file cannot be written.
            NotADirectoryError: If the parent path is invalid.
        """
        with_pebble_retry(lambda: path.write_text(content, mode=mode))


@dataclass(frozen=True)
class EtcdConfig:
    """Represent the etcd configuration."""

    endpoints: str
    cacert_path: str
    cert_path: str
    key_path: str


@dataclass(frozen=True)
class RollingOpsKeys:
    """Collection of etcd key prefixes used for rolling operations.

    Layout:
        /rollingops/{lock_name}/{cluster_id}/granted-unit/
        /rollingops/{lock_name}/{cluster_id}/{owner}/pending/
        /rollingops/{lock_name}/{cluster_id}/{owner}/inprogress/
        /rollingops/{lock_name}/{cluster_id}/{owner}/completed/

    The distributed lock key is cluster-scoped
    """

    ROOT: ClassVar[str] = '/rollingops'

    cluster_id: str
    owner: str
    lock_name: str = 'default'

    @property
    def cluster_prefix(self) -> str:
        """Etcd prefix corresponding to the cluster namespace."""
        return f'{self.ROOT}/{self.lock_name}/{self.cluster_id}/'

    @property
    def _owner_prefix(self) -> str:
        """Etcd prefix for all the queues belonging to an owner."""
        return f'{self.cluster_prefix}{self.owner}/'

    @property
    def lock_key(self) -> str:
        """Etcd key of the lock."""
        return f'{self.cluster_prefix}granted-unit/'

    @property
    def pending(self) -> str:
        """Prefix for operations waiting to be executed."""
        return f'{self._owner_prefix}pending/'

    @property
    def inprogress(self) -> str:
        """Prefix for operations currently being executed."""
        return f'{self._owner_prefix}inprogress/'

    @property
    def completed(self) -> str:
        """Prefix for operations that have finished execution."""
        return f'{self._owner_prefix}completed/'

    @classmethod
    def for_owner(cls, cluster_id: str, owner: str) -> 'RollingOpsKeys':
        """Create a set of keys for a given owner on a cluster."""
        return cls(cluster_id=cluster_id, owner=owner)
