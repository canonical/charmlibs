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
from charmlibs.rollingops.common._models import Operation, OperationResult
from charmlibs.rollingops.etcd._models import RollingOpsKeys

logger = logging.getLogger(__name__)

LOCK_LEASE_TTL = 60


class EtcdLease:
    """Manage the lifecycle of an etcd lease and its keep-alive process."""

    def __init__(self):
        self.id: str | None = None
        self.keepalive_proc: subprocess.Popen[str] | None = None

    def grant(self) -> None:
        """Create a new lease and start the keep-alive process."""
        res = etcdctl.run('lease', 'grant', str(LOCK_LEASE_TTL))
        # parse: "lease 694d9c9aeca3422a granted with TTL(1800s)"
        parts = res.split()
        self.id = parts[1]
        logger.info('%s', res)
        self._start_lease_keepalive()

    def revoke(self) -> None:
        """Revoke the current lease and stop the keep-alive process."""
        lease_id = self.id
        try:
            if self.id is not None:
                etcdctl.run('lease', 'revoke', self.id)
        except Exception:
            logger.exception('Fail to revoke lease %s.', lease_id)
            raise
        finally:
            try:
                self._stop_keepalive()
            except Exception:
                logger.exception('Fail to stop keepalive for lease %s.', lease_id)
            finally:
                self.id = None

    def _start_lease_keepalive(self) -> None:
        """Start the background process that keeps the lease alive."""
        lease_id = self.id
        if lease_id is None:
            logger.info('Lease ID is None. Keepalive for this lease cannot be started.')
            return
        etcdctl.ensure_initialized()
        self.keepalive_proc = subprocess.Popen(
            [etcdctl.ETCDCTL_CMD, 'lease', 'keep-alive', lease_id],
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
        try:
            self.keepalive_proc.terminate()
        except ProcessLookupError:
            # Already dead
            return
        except Exception:
            try:
                self.keepalive_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                logger.exception('Fail to stop keepalive for lease %s.')
                self.keepalive_proc.kill()
                return
        finally:
            self.keepalive_proc = None


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
        kv = etcdctl.get_first_key_value_pair(self.prefix)
        if kv is None:
            return None
        return Operation.from_dict(kv.value)

    def _peek_last(self) -> Operation | None:
        """Return the last operation in the queue without removing it."""
        kv = etcdctl.get_last_key_value_pair(self.prefix)
        if kv is None:
            return None
        return Operation.from_dict(kv.value)

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
        kv = etcdctl.get_first_key_value_pair(self.prefix)
        if kv is None:
            return False

        op_id = kv.key.split('/')[-1]
        new_key = f'{to_queue_prefix}{op_id}'
        data = json.dumps(kv.value)
        value_escaped = data.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        txn = f"""\
        value("{self.lock_key}") = "{self.owner}"
        version("{kv.key}") != "0"

        put "{new_key}" "{value_escaped}"
        del "{kv.key}"


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

    def watch(self) -> Operation:
        """Block until at least one operation exists and return it."""
        while True:
            kv = etcdctl.get_first_key_value_pair(self.prefix)
            if kv is not None:
                return Operation.from_dict(kv.value)
            time.sleep(10)

    def dequeue(self) -> bool:
        """Remove the first operation from the queue.

        The removal is performed using an etcd transaction that ensures
        the lock owner still holds the lock and the operation exists.

        Returns:
            True if the operation was removed successfully, otherwise False.
        """
        kv = etcdctl.get_first_key_value_pair(self.prefix)
        if kv is None:
            return False

        txn = f"""\
        value("{self.lock_key}") = "{self.owner}"
        version("{kv.key}") != "0"

        del "{kv.key}"


        """
        return etcdctl.txn(txn)

    def enqueue(self, operation: Operation) -> None:
        """Insert a new operation into the queue.

        The method avoids inserting duplicate operations by comparing
        the new operation with the last operation currently in the queue.

        Args:
            operation: Operation to insert.
        """
        old_operation = self._peek_last()

        if old_operation is not None and operation == old_operation:
            logger.info(
                'Operation %s not added to the etcd queue. '
                'It already exists in the back of the queue.',
                operation.callback_id,
            )
            return

        op_str = operation.to_string()
        key = f'{self.prefix}{operation.op_id}'
        etcdctl.run('put', key, op_str)
        logger.info('Operation %s added to the etcd queue.', operation.callback_id)

    def clear(self) -> None:
        etcdctl.run('del', self.prefix, '--prefix')


class WorkerOperationStore:
    """Background-worker view of etcd-backed rolling operations.

    This class is used by the background process that coordinates lock
    ownership and operation execution. It manages the lifecycle of queued
    operations across the etcd-backed queue prefixes:

    - pending: operations waiting to be claimed
    - in-progress: operations currently being executed
    - completed: operations that finished execution and await post-processing

    It provides worker-oriented methods to:
    - detect pending work
    - claim the next operation for execution
    - wait for completed operations
    - requeue or delete completed operations
    """

    def __init__(self, keys: RollingOpsKeys, owner: str):
        self._pending = EtcdOperationQueue(keys.pending, keys.lock_key, owner)
        self._inprogress = EtcdOperationQueue(keys.inprogress, keys.lock_key, owner)
        self._completed = EtcdOperationQueue(keys.completed, keys.lock_key, owner)

    def has_pending(self) -> bool:
        """Check whether there are pending operations.

        Returns:
            True if at least one operation exists in the pending queue,
            otherwise False.
        """
        return self._pending.peek() is not None

    def has_inprogress(self) -> bool:
        """Check whether there are in-progress operations.

        Returns:
            True if at least one operation exists in the inprogress queue,
            otherwise False.
        """
        return self._inprogress.peek() is not None

    def has_completed(self) -> bool:
        """Check whether there are completed operations.

        Returns:
            True if at least one operation exists in the completed queue,
            otherwise False.
        """
        return self._completed.peek() is not None

    def claim_next(self) -> bool:
        """Move the next pending operation to the in-progress queue.

        This operation is performed atomically and only succeeds if:
        - the lock is still held by this owner
        - the head of the pending queue has not changed

        Returns:
            True if the operation was successfully claimed,
            otherwise False.
        """
        return self._pending.move_head(self._inprogress.prefix)

    def wait_until_completed(self) -> Operation:
        """Block until at least one operation appears in the completed queue."""
        return self._completed.watch()

    def requeue_completed(self) -> bool:
        """Requeue the head completed operation back to the pending queue.

        This is typically used when an operation needs to be retried
        (e.g., RETRY_RELEASE or RETRY_HOLD semantics).

        Returns:
            True if the operation was successfully moved back to pending,
            otherwise False.
        """
        return self._completed.move_head(self._pending.prefix)

    def delete_completed(self) -> bool:
        """Remove the head operation from the completed queue.

        This is typically used when an operation has finished successfully
        and does not need to be retried.

        Returns:
            True if the operation was successfully removed,
            otherwise False.
        """
        return self._completed.dequeue()


class ManagerOperationStore:
    """Charm-facing interface for requesting and finalizing etcd-backed operations.

    This class is used by the RollingOps manager running inside the charm.
    It provides a narrow interface for interacting with the etcd-backed
    operation queues without exposing the full queue topology.

    The manager can use it to:
    - request a new operation
    - inspect the current in-progress operation
    - finalize an operation after execution

    Queue transitions and storage details remain encapsulated behind this API.
    """

    def __init__(self, keys: RollingOpsKeys, owner: str):
        self._pending = EtcdOperationQueue(keys.pending, keys.lock_key, owner)
        self._inprogress = EtcdOperationQueue(keys.inprogress, keys.lock_key, owner)
        self._completed = EtcdOperationQueue(keys.completed, keys.lock_key, owner)

    def request(self, operation: Operation) -> None:
        """Add a new operation to the pending queue.

        Duplicate operations (same callback_id and kwargs as the last queued
        operation) are not inserted.

        Args:
            operation: Operation to enqueue.
        """
        self._pending.enqueue(operation)

    def finalize(self, operation: Operation, result: OperationResult) -> bool:
        """Move an in-progress operation to the completed queue.

        This should be called after the operation has been executed and its
        result has been recorded.

        Args:
            operation: The operation currently in the in-progress queue.
            result: Result of the executions.
        """
        match result:
            case OperationResult.RETRY_HOLD:
                operation.retry_hold()
            case OperationResult.RETRY_RELEASE:
                operation.retry_release()
            case _:
                operation.complete()

        return self._inprogress.move_operation(self._completed.prefix, operation)

    def peek_current(self) -> Operation | None:
        """Peek the current in-progress operation."""
        return self._inprogress.peek()

    def has_pending_work(self) -> bool:
        return self.peek_current() is not None

    def clean_up(self) -> None:
        self._inprogress.clear()
        self._pending.clear()
        self._completed.clear()
