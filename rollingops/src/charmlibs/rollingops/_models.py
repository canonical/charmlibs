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

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, NamedTuple, TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from charmlibs.pathops import PebbleConnectionError

T = TypeVar('T')


class RollingOpsNoEtcdRelationError(Exception):
    """Raised if we are trying to process a lock, but do not appear to have a relation yet."""


class RollingOpsEtcdUnreachableError(Exception):
    """Raised if etcd server is unreachable."""


class RollingOpsEtcdNotConfiguredError(Exception):
    """Raised if etcd client has not been configured yet (env file does not exist)."""


class RollingOpsFileSystemError(Exception):
    """Raised if there is a problem when interacting with the filesystem."""


class RollingOpsInvalidLockRequestError(Exception):
    """Raised if the lock request is invalid."""


class RollingOpsDecodingError(Exception):
    """Raised if json content cannot be processed."""


class RollingOpsInvalidSecretContentError(Exception):
    """Raised if the content of a secret is invalid."""


@retry(
    retry=retry_if_exception_type(PebbleConnectionError),
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    reraise=True,
)
def with_pebble_retry[T](func: Callable[[], T]) -> T:
    return func()


class OperationResult(StrEnum):
    """Callback return values."""

    RELEASE = 'release'
    RETRY_RELEASE = 'retry-release'
    RETRY_HOLD = 'retry-hold'


class SharedCertificate(NamedTuple):
    """Represent the certificates shared within units of an app to connect to etcd."""

    certificate: str
    key: str
    ca: str


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
