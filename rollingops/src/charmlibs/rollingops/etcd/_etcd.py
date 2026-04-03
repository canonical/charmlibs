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

"""Classes that manage etcd concepts."""

import json
import logging
import subprocess
import time

import charmlibs.rollingops.etcd._etcdctl as etcdctl
from charmlibs.rollingops.common._models import Operation

logger = logging.getLogger(__name__)


class EtcdLease:
    """Manage the lifecycle of an etcd lease and its keep-alive process."""

    def __init__(self):
        self.id: str | None = None
        self.keepalive_proc: subprocess.Popen[str] | None = None

    def grant(self, ttl: int) -> None:
        """Create a new lease and start the keep-alive process.

        Args:
            ttl: Time-to-live of the lease in seconds.
        """
        res = etcdctl.run('lease', 'grant', str(ttl))
        if res is None:  # handle error case
            return
        # parse: "lease 694d9c9aeca3422a granted with TTL(1800s)"
        parts = res.split()
        self.id = parts[1]
        logger.info('%s', res)
        self._start_lease_keepalive()

    def revoke(self) -> None:
        """Revoke the current lease and stop the keep-alive process."""
        if self.id is not None:
            etcdctl.run('lease', 'revoke', self.id)
            # handle error case
            self.id = None
            logger.info('Lease %s revoked.', self.id)
        self._stop_keepalive()

    def _start_lease_keepalive(self) -> None:
        """Start the background process that keeps the lease alive."""
        lease_id = self.id
        if lease_id is None:
            logger.info('Lease ID is None. Keepalive for this lease cannot be started.')
            return
        etcdctl.ensure_initialized()
        self.keepalive_proc = subprocess.Popen(
            ['etcdctl', 'lease', 'keep-alive', lease_id],
            env=etcdctl.load_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )  # handle error case?
        logger.info('Keepalive started for lease %s.', self.id)

    def _stop_keepalive(self) -> None:
        """Terminate the keep-alive subprocess if it is running."""
        if self.keepalive_proc is None:
            return
        self.keepalive_proc.terminate()
        try:
            self.keepalive_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.keepalive_proc.kill()
            self.keepalive_proc.wait(timeout=2)
        self.keepalive_proc = None
        logger.info('Keepalive stopped for lease %s.', self.id)


class EtcdLock:
    """Distributed lock implementation backed by etcd.

    The lock is represented by a key whose value identifies the current owner.

    Lock acquisition and release are performed using transactions to
    ensure atomicity.

    The lock is attached to an etcd lease so that it is
    automatically released if the owner stops refreshing the lease.
    """

    def __init__(self, lock_key: str, owner: str):
        self.lock_key = lock_key
        self.owner = owner

    def try_acquire(self, lease_id: str) -> bool:
        """Attempt to acquire the lock.

        This method uses an etcd transaction that succeeds only if the
        lock key does not yet exist. If successful, the lock key is created with the current
        owner as its value and is attached to the provided lease.

        Args:
            lease_id: ID of the etcd lease to associate with the lock.

        Returns:
            True if the lock was successfully acquired, otherwise False.
        """
        txn = f"""\
        version("{self.lock_key}") = "0"

        put "{self.lock_key}" "{self.owner}" --lease={lease_id}


        """
        return etcdctl.txn(txn)

    def release(self) -> None:
        """Release the lock if it is currently held by this owner.

        The lock is removed only if the value of the lock key matches
        the current owner. This prevents one process from accidentally
        releasing a lock held by another owner.
        """
        txn = f"""\
        value("{self.lock_key}") = "{self.owner}"

        del "{self.lock_key}"


        """
        etcdctl.txn(txn)

    def is_held(self) -> bool:
        """Check whether the lock is currently held by this owner."""
        res = etcdctl.run('get', self.lock_key, '--print-value-only')

        if res is None:
            return False

        return res == self.owner


class EtcdOperationQueue:
    """Queue abstraction for operations stored in etcd.

    This class represents a queue of operations stored under a common
    key prefix in etcd. Each operation is stored as a key-value pair
    where the key encodes the operation identifier and ordering, and
    the value contains the serialized operation data.
    """

    def __init__(self, prefix: str, lock_key: str, owner: str):
        self.prefix = prefix
        self.lock_key = lock_key
        self.owner = owner

    def peek(self) -> Operation | None:
        """Return the first operation in the queue without removing it."""
        kv = etcdctl.get_first_key_value(self.prefix)
        if kv is None:
            return None
        _, value = kv
        return Operation.from_dict(value)

    def _peek_last(self) -> Operation | None:
        """Return the last operation in the queue without removing it."""
        kv = etcdctl.get_last_key_value(self.prefix)
        if kv is None:
            return None
        _, value = kv
        return Operation.from_dict(value)

    def move_head(self, to_queue_prefix: str) -> bool:
        """Move the first operation in the queue to another queue.

        This operation is performed atomically using an etcd transaction.
        The transaction succeeds only if:
        - The lock is currently held by the configured owner.
        - The head operation still exists.

        Args:
            to_queue_prefix: Destination queue prefix.

        Returns:
            True if the operation was moved successfully, otherwise False.
        """
        kv = etcdctl.get_first_key_value(self.prefix)
        if kv is None:
            return False
        key, value = kv

        op_id = key.split('/')[-1]
        new_key = f'{to_queue_prefix}{op_id}'
        data = json.dumps(value)
        value_escaped = data.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        txn = f"""\
        value("{self.lock_key}") = "{self.owner}"
        version("{key}") != "0"

        put "{new_key}" "{value_escaped}"
        del "{key}"


        """
        return etcdctl.txn(txn)

    def move_operation(self, to_queue_prefix: str, operation: Operation) -> bool:
        """Move a specific operation from this queue to another queue.

        The operation is identified using its operation ID and moved
        atomically via an etcd transaction.

        Args:
            to_queue_prefix: Destination queue prefix.
            operation: Operation to move.

        Returns:
            True if the operation was successfully moved, otherwise False.
        """
        old_key = f'{self.prefix}{operation.op_id}'
        new_key = f'{to_queue_prefix}{operation.op_id}'

        data = operation.to_string()
        value_escaped = data.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        txn = f"""\
        value("{self.lock_key}") = "{self.owner}"
        version("{old_key}") != "0"

        put "{new_key}" "{value_escaped}"
        del "{old_key}"


        """
        return etcdctl.txn(txn)

    def watch(self) -> None:
        """Block until at least one operation exists in the queue.

        This method periodically polls the queue prefix and returns once
        an operation is detected
        """
        while True:
            if etcdctl.get_first_key_value(self.prefix) is not None:
                return
            time.sleep(30)

    def dequeue(self) -> bool:
        """Remove the first operation from the queue.

        The removal is performed using an etcd transaction that ensures
        the lock owner still holds the lock and the operation exists.

        Returns:
            True if the operation was removed successfully, otherwise False.
        """
        kv = etcdctl.get_first_key_value(self.prefix)
        if kv is None:
            return False
        key, _ = kv

        txn = f"""\
        value("{self.lock_key}") = "{self.owner}"
        version("{key}") != "0"

        del "{key}"


        """
        return etcdctl.txn(txn)

    def enqueue(self, operation: Operation) -> bool:
        """Insert a new operation into the queue.

        The method avoids inserting duplicate operations by comparing
        the new operation with the last operation currently in the queue.

        Args:
            operation: Operation to insert.

        Returns:
            True if the operation was inserted, or False if it was skipped
            because it duplicates the most recent operation.
        """
        old_operation = self._peek_last()

        if old_operation is not None and operation == old_operation:
            return False

        op_str = operation.to_string()
        key = f'{self.prefix}{operation.op_id}'
        res = etcdctl.run('put', key, op_str)
        if res is None:
            return False
        return True
