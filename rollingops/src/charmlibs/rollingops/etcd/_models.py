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

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, TypeVar

from charmlibs.interfaces.tls_certificates import Certificate, PrivateKey
from charmlibs.pathops import LocalPath
from charmlibs.rollingops.common._exceptions import RollingOpsDecodingError
from charmlibs.rollingops.common._models import (
    OperationResult,
    now_timestamp,
    parse_timestamp,
    with_pebble_retry,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


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


@dataclass
class EtcdOperation:
    """A single queued operation."""

    callback_id: str
    requested_at: datetime
    max_retry: int | None
    attempt: int
    result: OperationResult | None
    kwargs: dict[str, Any] = field(default_factory=dict[str, Any])

    @classmethod
    def _validate_fields(
        cls, callback_id: Any, kwargs: Any, requested_at: Any, max_retry: Any, attempt: Any
    ) -> None:
        """Validate the class attributes."""
        if not isinstance(callback_id, str) or not callback_id.strip():
            raise ValueError('callback_id must be a non-empty string')

        if not isinstance(kwargs, dict):
            raise ValueError('kwargs must be a dict')
        try:
            json.dumps(kwargs)
        except TypeError as e:
            raise ValueError(f'kwargs must be JSON-serializable: {e}') from e

        if not isinstance(requested_at, datetime):
            raise ValueError('requested_at must be a datetime')

        if max_retry is not None:
            if not isinstance(max_retry, int):
                raise ValueError('max_retry must be an int')
            if max_retry < 0:
                raise ValueError('max_retry must be >= 0')

        if not isinstance(attempt, int):
            raise ValueError('attempt must be an int')
        if attempt < 0:
            raise ValueError('attempt must be >= 0')

    def __post_init__(self) -> None:
        """Validate the class attributes."""
        self._validate_fields(
            self.callback_id,
            self.kwargs,
            self.requested_at,
            self.max_retry,
            self.attempt,
        )

    @classmethod
    def create(
        cls,
        callback_id: str,
        kwargs: dict[str, Any],
        max_retry: int | None = None,
    ) -> 'EtcdOperation':
        """Create a new operation from a callback id and kwargs."""
        return cls(
            callback_id=callback_id,
            kwargs=kwargs,
            requested_at=now_timestamp(),
            max_retry=max_retry,
            attempt=0,
            result=None,
        )

    def _to_dict(self) -> dict[str, str]:
        """Dict form (string-only values)."""
        return {
            'callback_id': self.callback_id,
            'kwargs': self._kwargs_to_json(),
            'requested_at': self.requested_at.isoformat(),
            'max_retry': '' if self.max_retry is None else str(self.max_retry),
            'attempt': str(self.attempt),
            'result': '' if self.result is None else self.result,
        }

    def to_string(self) -> str:
        """Serialize to a string suitable for a Juju databag."""
        return json.dumps(self._to_dict(), separators=(',', ':'))

    def increase_attempt(self) -> None:
        """Increment the attempt counter."""
        self.attempt += 1

    def is_max_retry_reached(self) -> bool:
        """Return True if attempt exceeds max_retry (unless max_retry is None)."""
        if self.max_retry is None:
            return False
        return self.attempt > self.max_retry

    def complete(self) -> None:
        """Mark the operation as completed to indicate the lock should be released."""
        self.increase_attempt()
        self.result = OperationResult.RELEASE

    def retry_release(self) -> None:
        """Mark the operation for retry if it has not reached the max retry."""
        self.increase_attempt()
        if self.is_max_retry_reached():
            logger.warning('Operation max retry reached. Dropping.')
            self.result = OperationResult.RELEASE
        else:
            self.result = OperationResult.RETRY_RELEASE

    def retry_hold(self) -> None:
        """Mark the operation for retry if it has not reached the max retry."""
        self.increase_attempt()
        if self.is_max_retry_reached():
            self.result = OperationResult.RELEASE
            logger.warning('Operation max retry reached. Dropping.')
        else:
            self.result = OperationResult.RETRY_HOLD

    @property
    def op_id(self) -> str:
        """Return the unique identifier for this operation."""
        return f'{self.requested_at.isoformat()}-{self.callback_id}'

    @classmethod
    def from_string(cls, data: str) -> 'EtcdOperation':
        """Deserialize from a Juju databag string.

        Raises:
            RollingOpsDecodingError: if data cannot be deserialized.
        """
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error('Failed to deserialize Operation from %s: %s', data, e)
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an Operation'
            ) from e
        return cls.from_dict(obj)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> 'EtcdOperation':
        """Create an Operation from its dict (etcd) representation."""
        try:
            return cls(
                callback_id=data['callback_id'],
                requested_at=parse_timestamp(data['requested_at']),  # type: ignore[reportArgumentType]
                max_retry=int(data['max_retry']) if data.get('max_retry') else None,
                attempt=int(data['attempt']),
                kwargs=json.loads(data['kwargs']) if data.get('kwargs') else {},
                result=OperationResult(data['result']) if data.get('result') else None,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error('Failed to deserialize Operation from %s: %s', data, e)
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an Operation'
            ) from e

    def _kwargs_to_json(self) -> str:
        """Deterministic JSON serialization for kwargs."""
        return json.dumps(self.kwargs, sort_keys=True, separators=(',', ':'))

    def __eq__(self, other: object) -> bool:
        """Equal for the operation."""
        if not isinstance(other, EtcdOperation):
            return False
        return self.callback_id == other.callback_id and self.kwargs == other.kwargs

    def __hash__(self) -> int:
        """Hash for the operation."""
        return hash((self.callback_id, self._kwargs_to_json()))
