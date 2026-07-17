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
units of a Juju application.

It supports two execution modes:

1. Peer-based (application level)
   Uses peer relations to coordinate operations within a single application.
   The leader unit schedules execution and ensures that operations are
   performed sequentially (at most one unit at a time).

2. Etcd-based (cluster level)
   Uses etcd as a distributed coordination backend. Units independently
   compete for the lock using etcd primitives, enabling coordination across
   applications or clusters.

When etcd is configured, it is the primary backend, but it depends on the peer
relation for internal state management. If etcd becomes unavailable or encounters
errors, the library automatically falls back to the peer-based backend to ensure
operations can continue.

Typical use cases:

- Rolling restarts of application units
- Safe configuration changes requiring sequential execution
- Maintenance tasks that must not run concurrently
- Cluster-wide operations coordinated via etcd

Known current limitations
--------------------------

- **Peer-only mode**
  Supported for both machine (VM) and Kubernetes charms.

- **Etcd-based mode**
  Supported only for machine (VM) charms.

This is due to current ecosystem constraints:

- The etcd charm is only available for VM deployments
- Cross-model relations between Kubernetes and VM charms have limitations,
  particularly when sharing secrets over relations.

As a result, Kubernetes charms should use the peer-based backend only.

We are aware of these limitations and are actively working to address them.

Execution model
---------------

RollingOps is based on a **lock-driven execution model**.

Units do not execute operations immediately. Instead, they:

- Request a lock
- Provide a callback identifier and arguments
- The operation is queued locally
- When the lock is granted, the callback is executed asynchronously

At any time, only one unit holds the lock and executes one operation.

Operation queue
---------------

Each unit maintains a queue of pending operations. Only the head of the queue
is executed when the lock is granted.

New operations follow these deduplication rules:

- Same operation + same arguments
  → If the latest queued operation has the same `callback_id` and arguments,
  the new request is ignored.

- Same operation + different arguments
  → The new operation is added to the queue.

- Different operation
  → The new operation is added to the queue.


Core concepts
-------------

Asynchronous lock (recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The primary mechanism. Operations are enqueued and executed later when the
lock is granted. This avoids blocking Juju hooks.

Synchronous lock (special-case)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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


Callback contract
^^^^^^^^^^^^^^^^^

Asynchronous operations are defined as callbacks and registered via the
``callback_targets`` parameter when initializing ``RollingOpsManager``.
This parameter is a mapping of string identifiers to bound methods on the
charm.

Callbacks must follow this signature::

    def <callback>(self, **kwargs) -> OperationResult

Callbacks must be idempotent and safe to run multiple times, as they may be
retried due to failures or hook replays. They must not interact directly with
the locking mechanism (e.g. requesting locks, mutating the peer relation
databag used by the library, emitting relation events, or deferring execution).

Operation result
~~~~~~~~~~~~~~~~

Callbacks must return an `OperationResult`:

- `RELEASE`
  → Execution succeeded, release the lock

- `RETRY_RELEASE`
  → Execution failed, retry later after releasing the lock (other units may proceed)

- `RETRY_HOLD`
  → Execution failed, retry while keeping the lock

- If the callback returns None or an invalid value, the lock is released.
- If the callback raises an exception, it is considered as a `RETRY_RELEASE`.

Arguments:
~~~~~~~~~~

The callback arguments (``kwargs``) must be JSON-serializable, as they are
stored in the peer relation databag.

Peer-based scheduling
^^^^^^^^^^^^^^^^^^^^^

In peer-based mode, the leader unit acts as scheduler and grants the lock.

Scheduling is priority-based, from highest to lowest:

1. Retry-hold operations
2. First-time requests
3. Retry-release operations

Rules:

- If a unit holds the lock → no new grant
- Otherwise → select next unit based on priority

The selected unit executes the head of its queue.

Etcd-based coordination
^^^^^^^^^^^^^^^^^^^^^^^^

When etcd is used:

- Units independently attempt to acquire the lock via etcd
- There is no central scheduler
- Execution remains mutually exclusive (one lock holder)

Etcd setup
----------

To use etcd-backed operations:

1. Deploy an ``charmed-etcd`` application
2. Integrate it with a TLS certificates provider that implements the
   `tls-certificates`` interface
3. Relate ``charmed-etcd`` to your charm

The etcd-based functionality requires the etcdctl binary to be present
in the charm.

Including etcdctl in your charm
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The etcd-backed functionality relies on the ``etcdctl`` binary being available
inside the charm machine. This binary is not provided automatically
and must be included as part of your charm build.

You can add it in your ``charmcraft.yaml`` using a build part::

    parts:
      etcdctl:
        plugin: make
        source: https://git.launchpad.net/etcd
        source-type: git
        source-tag: lp-v3.6.10
        build-snaps:
          - go/latest/stable
        override-build: |
          set -eux
          make build
          install -Dm755 bin/etcdctl "${CRAFT_PART_INSTALL}/usr/bin/etcdctl"
        prime:
          - usr/bin/etcdctl

This makes ``etcdctl`` available at runtime under
``<charm-dir>/usr/bin/etcdctl``.

This path is expected by the library, so do not install the binary in a
different location.

Make sure the binary is present and executable, as it is required for
communication with the etcd backend.


Cluster identifier
^^^^^^^^^^^^^^^^^^

The ``cluster_id`` parameter is used to scope etcd-backed coordination.

All applications using the same ``cluster_id`` will share the same lock,
allowing rolling operations to be coordinated across multiple applications.

The ``cluster_id`` does not need to be hardcoded and may be provided dynamically
at runtime.

The ``RollingOpsManager`` can be initialized without a ``cluster_id`` and will
operate using the peer backend until the identifier becomes available.

Once the ``cluster_id`` is set, etcd-backed coordination will be used
automatically if the etcd relation is configured.

Do not provide a ``cluster_id`` without a ``etcd_relation_name``.


Integrations
--------------

Example relations::

    peers:
      rollingops-peers:
        interface: rollingops-peers

    requires:
      etcd:
        interface: etcd_client
        limit: 1
        optional: true

Nothe that the peer relation is mandatory even if we are integrating
with etcd.


Runtime storage (``base_dir``)
-------------------------------

RollingOps requires a writable base directory to store runtime files
used during operation. This directory is configured through the ``base_dir``
parameter.

By default, RollingOps uses: ``/var/lib/rollingops``.

If the directory does not exist, RollingOps will attempt to create it automatically.
The process running RollingOps must have permission to write to ``base_dir``.

For Kubernetes charms, ``base_dir`` must refer to a writable path inside the charm container
filesystem.

What is stored in ``base_dir``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

RollingOps uses this directory for runtime artifacts, including:

- logs generated by background processes
- etcd connection assets, such as client certificates and related configuration files


Usage
----------

Provide an implementation of ``SyncLockBackend``::

    from charmlibs.rollingops import SyncLockBackend

    class MySyncLockBackend(SyncLockBackend):
        def __init__(self, path: str = "/tmp/rollingops.lock"):
            self._path = path

        def acquire(self, timeout: int | None) -> None:
            # Provide implementation

        def release(self) -> None:
            # Provide implementation

Use the rollingops library in your charm::

    from charmlibs.rollingops import RollingOpsManager, OperationResult

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

        # This is a callback
        def _restart_unit(self) -> OperationResult:
            # logic executed under rolling coordination
            return OperationResult.RELEASE

        # This is an async lock request
        def _on_config_changed(self, event):
            self.rollingops.request_async_lock("restart", kwargs={'delay': delay}, max_retry=2)

        # This is a sync lock request (to be used only when deferring is not possible)
        def _on_stop(self, event):
            with self.rollingops.acquire_sync_lock(
                backend_id="my-lock",
                timeout=300,
            ):
                # Execute the critial section
                self._restart_unit()

            # Lock is automatically released

If you want to used it on peer-only mode, skip the ``etcd_relation_name`` and
``cluster_id`` parameters in the ``RollingOpsManager`` constructor::

    from charmlibs.rollingops import RollingOpsManager

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
                sync_lock_targets={
                    "my-lock" : my_sync_backend,
                },
            )

Beware that the ``sync_lock_targets`` is also optional, but if no provided, the
sync lock cannot be used

Migration from v0
-----------------

The charmlibs-rollingops library introduces a more robust and predictable execution model,
addressing several limitations of the previous implementation.

In v0, coordination issues could lead to unexpected or unsafe behavior:

- Deferred callbacks could break mutual exclusion, causing operations to run without a lock
- Multiple lock requests could overwrite each other, silently dropping operations
- Exceptions during callbacks could leave the system in a stuck state.

The new version introduces:

- Safe handling of deferred callbacks, preserving lock guarantees
- A per-unit operation queue, ensuring all requests are preserved and executed
- Explicit retry semantics, allowing controlled and predictable failure handling
- Support for rolling operations across multiple applications (via etcd)

Key migration changes:

- New ``RollingOpsManager`` constructor
  Replace ``relation`` and ``callback`` with ``peer_relation_name`` and
  ``callback_targets`` (mapping of callback IDs to methods).

- New callback signature and contract
  Callbacks no longer receive an event, must accept ``**kwargs``, and must
  return an ``OperationResult``.

- New async lock request API
  Replace event emission (``acquire_lock.emit``) with
  ``request_async_lock(callback_id=..., kwargs=..., max_retry=...)``.


Manager initialization
^^^^^^^^^^^^^^^^^^^^^^

Before, the manager accepted a single relation name and a single callback::

    from charms.rolling_ops.v0.rollingops import RollingOpsManager

    self.restart_manager = RollingOpsManager(
        charm=self,
        relation="restart",
        callback=self._restart,
    )

Now, callbacks are registered explicitly using callback_targets.
Each callback is identified by a string key::

    from charmlibs.rollingops import RollingOpsManager

    self.rollingops = RollingOpsManager(
        charm=self,
        peer_relation_name="restart",
        callback_targets={
            "restart": self._restart,
            "custom-restart": self._custom_restart,
        },
    )


Requesting an asynchronous lock
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Before, lock acquisition was triggered by emitting the library event::

    def _on_restart_action(self, event):
        self.on[self.restart_manager.name].acquire_lock.emit()

    def _on_custom_restart_action(self, event):
        self.on[self.restart_manager.name].acquire_lock.emit(
            callback_override="_custom_restart"
    )


Now, request the lock directly through ``request_async_lock`` and pass the
callback identifier::

    def _on_restart_action(self, event):
        delay = event.params.get("delay")
        self.rollingops.request_async_lock(
            callback_id="restart",
            kwargs={"delay": delay},
            max-retry=1,
        )

    def _on_custom_restart_action(self, event):
        delay = event.params.get("delay")
        self.rollingops.request_async_lock(
            callback_id="custom-restart",
            kwargs={"delay": delay},
        )


Now, arguments can be passed directly through kwargs when requesting the lock.
You can also use ``max_retry`` when requesting the lock to limit the number of
retry attempts in case of failure.

Retries and callback return value
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Callbacks must now return an ``OperationResult`` so the library knows whether
to release the lock or retry the operation.

Before::

    def _restart(self, event):
        if self._stored.delay:
            time.sleep(int(self._stored.delay))

        self.model.get_relation(self.restart_manager.name).data[self.unit].update({
            "restart-type": "restart"
        })

Now::

    from charmlibs.rollingops import OperationResult

    def _restart(self, delay=None) -> OperationResult:
        if not self.is_ready():
            return OperationResult.RETRY_RELEASE
        if delay:
            time.sleep(int(delay))

        self._stored.restarted = True

        self.model.get_relation("restart").data[self.unit].update({
            "restart-type": "restart"
        })

        return OperationResult.RELEASE

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
    OperationResult,
    ProcessingBackend,
    RollingOpsState,
    RollingOpsStatus,
    SyncLockBackend,
)
from ._rollingops_manager import RollingOpsManager
from ._version import __version__ as __version__

__all__ = (
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
