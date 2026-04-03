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
from charmlibs.rollingops.etcd._etcd import (
    EtcdLease,
    EtcdLock,
    WorkerOperationStore,
)
from charmlibs.rollingops.etcd._models import RollingOpsKeys


def _dispatch_lock_granted(run_cmd: str, unit_name: str, charm_dir: str) -> None:
    """Dispatch the rollingops_lock_granted hook."""
    dispatch_sub_cmd = f'JUJU_DISPATCH_PATH=hooks/rollingops_lock_granted {charm_dir}/dispatch'
    res = subprocess.run([run_cmd, '-u', unit_name, dispatch_sub_cmd], check=False)
    res.check_returncode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-cmd', required=True)
    parser.add_argument('--unit-name', required=True)
    parser.add_argument('--charm-dir', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--cluster-id', required=True)
    args = parser.parse_args()

    lock_lease_ttl = 60
    acquire_retry_sleep = 15

    time.sleep(10)

    keys = RollingOpsKeys.for_owner(args.cluster_id, args.owner)
    lock = EtcdLock(keys.lock_key, args.owner)
    lease = EtcdLease()
    operations = WorkerOperationStore(keys, args.owner)

    while True:
        if not operations.has_pending():
            time.sleep(acquire_retry_sleep)
            continue

        if not lock.is_held():
            if lease.id is None:
                lease.grant(lock_lease_ttl)

            lease_id = lease.id
            if lease_id is None:
                time.sleep(acquire_retry_sleep)
                continue

            if not lock.try_acquire(lease_id):
                time.sleep(acquire_retry_sleep)
                continue

            print('Lock granted')

        if not operations.claim_next():
            time.sleep(acquire_retry_sleep)
            continue

        print('dispatch hook')
        _dispatch_lock_granted(args.run_cmd, args.unit_name, args.charm_dir)

        operations.wait_until_completed()
        operation = operations.peek_completed()
        if operation is None:
            print('completed queue watch returned no operation')
            time.sleep(acquire_retry_sleep)
            continue

        match operation.result:
            case OperationResult.RETRY_HOLD:
                operations.requeue_completed()
                continue

            case OperationResult.RETRY_RELEASE:
                operations.requeue_completed()

            case _:
                operations.delete_completed()

        lease.revoke()
        lock.release()

        if not operations.has_pending():
            break

        time.sleep(acquire_retry_sleep)


if __name__ == '__main__':
    main()
