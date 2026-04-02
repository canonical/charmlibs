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

import argparse
import subprocess
import time

from charmlibs.rollingops.common._models import OperationResult
from charmlibs.rollingops.etcd._etcd import EtcdLease, EtcdLock, EtcdOperationQueue
from charmlibs.rollingops.etcd._models import RollingOpsKeys


def main():
    """Etcd rollingops background process to manage locks and operations."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-cmd', required=True)
    parser.add_argument('--unit-name', required=True)
    parser.add_argument('--charm-dir', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--cluster-id', required=True)
    args = parser.parse_args()

    time.sleep(10)

    keys = RollingOpsKeys.for_owner(args.cluster_id, args.owner)
    lock_lease_ttl = 60
    acquire_retry_sleep = 15
    lock = EtcdLock(keys.lock_key, args.owner)
    pending_queue = EtcdOperationQueue(keys.pending, keys.lock_key, args.owner)
    completed_queue = EtcdOperationQueue(keys.completed, keys.lock_key, args.owner)
    lease = EtcdLease()

    while True:
        if not pending_queue.peek():
            time.sleep(acquire_retry_sleep)
            continue

        if not lock.is_held():
            if lease.id is None:
                lease.grant(lock_lease_ttl)

            if lock.try_acquire(lease.id):  # pyright: ignore[reportArgumentType]
                print('Lock granted')

            else:
                time.sleep(acquire_retry_sleep)
                continue

        moved = pending_queue.move_head(keys.inprogress)
        if moved:
            # dispatch hook
            print('dispatch hook')
            dispatch_sub_cmd = (
                f'JUJU_DISPATCH_PATH=hooks/rollingops_lock_granted {args.charm_dir}/dispatch'
            )
            res = subprocess.run([args.run_cmd, '-u', args.unit_name, dispatch_sub_cmd])
            res.check_returncode()
        else:
            time.sleep(acquire_retry_sleep)
            continue

        completed_queue.watch()
        operation = completed_queue.peek()
        if operation is None:
            print('watc completed return None')
            continue

        match operation.result:
            case OperationResult.RETRY_HOLD:
                completed_queue.move_head(keys.pending)
                continue

            case OperationResult.RETRY_RELEASE:
                completed_queue.move_head(keys.pending)

            case _:
                print(completed_queue.dequeue())

        lease.revoke()
        lock.release()
        if not pending_queue.peek():
            break
        time.sleep(acquire_retry_sleep)


if __name__ == '__main__':
    main()
