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

"""RollingOps: coordinated rolling operations for Juju charms.

This library provides a unified API to coordinate rolling operations across
units of a Juju application. It supports two execution modes:

1. Peer-based (application level)
   Uses peer relations to coordinate operations within a single application.
   Ensures that disruptive actions (e.g. restarts, reconfigurations) are
   executed sequentially, with at most one unit operating at a time.
   The leader schedules work and guarantees fairness and safe progression.

2. Etcd-based (cluster level)
   Uses etcd as a distributed coordination backend to provide asynchronous,
   non-blocking mutual exclusion across units. Each unit runs a background
   worker that manages lock acquisition, lease renewal, and execution of
   operations without blocking Juju hooks. This is suitable for long-running
   tasks across a cluster.

Core concepts
-------------

Asynchronous lock (primary mechanism)
    The main functionality of this library is the asynchronous lock.
    Callers enqueue an operation by providing a callback target. The library
    ensures that the operation is executed later, in mutual exclusion,
    without blocking the current Juju hook. This is the recommended approach
    for most operations.

Synchronous lock (special-case mechanism)
    A synchronous lock is provided for scenarios where deferring is not
    possible (e.g. teardown or finalization paths). In this mode, the hook is
    blocked until the lock is granted, and the critical section is executed
    directly by the charm's code rather than by the library. Because this
    blocks hook execution, it should be used carefully.

    When etcd is integrated, it provides the synchronous locking mechanism.
    If etcd is not integrated (or a fallback to peer coordination is required),
    the library will attempt to use a peer-based backend. However, the peer
    backend does not provide a native synchronous lock, as peer relations
    cannot be relied upon during teardown.

    To support these cases, users can optionally provide custom synchronous
    lock backends via the ``sync_lock_targets`` parameter when initializing
    ``RollingOpsManager``. Each backend must implement ``SyncLockBackend``.

Typical use cases:
- Rolling restarts of application units
- Safe configuration changes requiring sequential execution
- Maintenance tasks that must not run concurrently
- Cluster-wide operations coordinated via etcd

Basic usage:

    from charmlibs.rollingops import RollingOpsManager, SyncLockBackend, OperationResult

    class MySyncLockBackend(SyncLockBackend):
        def __init__(self, path: str = "/tmp/rollingops.lock"):
            self._path = path

        def acquire(self, timeout: int | None) -> None:
            # Provide implementation

        def release(self) -> None:
            # Provide implementation

    class MyCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)

            my_sync_backend = MySyncLockBackend()
            self.rollingops = RollingOpsManager(
                charm=self,
                callback_targets={
                    "restart": self._restart_unit,
                },
                peer_relation_name="my-peers",
                etcd_relation_name="etcd",
                cluster_id="my-cluster",
                sync_lock_targets={
                    "my-lock" : my_sync_backend,
                },
            )

        def _restart_unit(self) -> OperationResult:
            # logic executed under rolling coordination
            return OperationResult.RELEASE

        def _on_config_changed(self, event):
            # asynchronous (recommended)
            self.rollingops.request_async_lock("restart")

        def _on_stop(self, event):
            # synchronous (only when deferring is not possible)
            with self.rollingops.acquire_sync_lock(
                backend_id="my-lock",
                timeout=300,
            ):
                self._restart_unit()


Etcd setup
----------

To use etcd-backed rolling operations, deploy an etcd application and a
certificates provider that implements the ``tls-certificates`` interface
according to your deployment requirements.

The certificates provider must be integrated with etcd first. Then integrate
etcd with the charm using this library.

At the moment, etcd is available as a VM operator only. There is no Kubernetes
etcd operator. If your charm is a VM charm, etcd can be deployed in the same
model and related directly to your charm. If your charm runs on Kubernetes,
deploy etcd in another VM model/cloud/controller, offer the etcd relation,
consume the offer from the Kubernetes model, and integrate your charm with
that consumed offer.

Integrations
--------------------------

Integration with etcd is optional. If you only need application-level
coordination, you can rely on the peer relation alone and omit both
``etcd_relation_name`` and ``cluster_id`` when initializing
``RollingOpsManager``.

Note that the etcd-based functionality still depends on the peer relation
for internal coordination and state management, so the peer relation must
always be configured.

When etcd is configured, the library will prefer etcd-backed coordination
and fall back to the peer-based mechanism if etcd is unavailable.

The relations can be added to the charm as follows:


    peers:
      rollingops-peers:
        interface: rollingops-peers

    requires:
      etcd:
        interface: etcd_client
        limit: 1
        optional: true

"""

from ._common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsError,
    RollingOpsEtcdctlError,
    RollingOpsEtcdNotConfiguredError,
    RollingOpsFileSystemError,
    RollingOpsInvalidLockRequestError,
    RollingOpsInvalidSecretContentError,
    RollingOpsLibMissingError,
    RollingOpsNoRelationError,
    RollingOpsSyncLockError,
)
from ._common._models import (
    Operation,
    OperationQueue,
    OperationResult,
    ProcessingBackend,
    RollingOpsState,
    RollingOpsStatus,
    SyncLockBackend,
)
from ._rollingops_manager import RollingOpsManager
from ._version import __version__ as __version__

__all__ = (
    'Operation',
    'OperationQueue',
    'OperationResult',
    'ProcessingBackend',
    'RollingOpsDecodingError',
    'RollingOpsError',
    'RollingOpsEtcdNotConfiguredError',
    'RollingOpsEtcdctlError',
    'RollingOpsFileSystemError',
    'RollingOpsInvalidLockRequestError',
    'RollingOpsInvalidSecretContentError',
    'RollingOpsLibMissingError',
    'RollingOpsManager',
    'RollingOpsNoRelationError',
    'RollingOpsState',
    'RollingOpsStatus',
    'RollingOpsSyncLockError',
    'SyncLockBackend',
)
