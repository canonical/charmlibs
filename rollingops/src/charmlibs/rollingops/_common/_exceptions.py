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

"""Exceptions used in rollingops."""


class RollingOpsError(Exception):
    """General rollingops error."""


class RollingOpsNoRelationError(RollingOpsError):
    """Raised if we are trying to process a lock, but do not appear to have a relation yet."""


class RollingOpsNoEtcdRelationError(RollingOpsNoRelationError):
    """Raised if we are trying to process a lock, but do not appear to have a relation yet."""


class RollingOpsFileSystemError(RollingOpsError):
    """Raised if there is a problem when interacting with the filesystem."""


class RollingOpsInvalidLockRequestError(RollingOpsError):
    """Raised if the lock request is invalid."""


class RollingOpsDecodingError(RollingOpsError):
    """Raised if json content cannot be processed."""


class RollingOpsInvalidSecretContentError(RollingOpsError):
    """Raised if the content of a secret is invalid."""


class RollingOpsLibMissingError(RollingOpsError):
    """Raised if the path to the libraries cannot be resolved."""


class RollingOpsEtcdctlError(RollingOpsError):
    """Base exception for etcdctl command failures."""


class RollingOpsEtcdctlRetryableError(RollingOpsEtcdctlError):
    """A transient etcdctl failure that may succeed on retry."""


class RollingOpsEtcdNotConfiguredError(RollingOpsEtcdctlError):
    """Raised if etcd client has not been configured yet (env file does not exist)."""


class RollingOpsEtcdctlFatalError(RollingOpsEtcdctlError):
    """A non-retryable etcdctl failure."""


class RollingOpsEtcdctlParseError(RollingOpsEtcdctlError):
    """Raised when etcdctl output cannot be parsed."""


class RollingOpsSyncLockError(RollingOpsError):
    """Raised when there is an error during sync lock execution."""


class RollingOpsEtcdTransactionError(RollingOpsError):
    """Raised when an etcd transaction fails."""
