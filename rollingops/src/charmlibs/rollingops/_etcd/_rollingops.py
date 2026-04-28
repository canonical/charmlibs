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
import logging
import time

from charmlibs import pathops
from charmlibs.rollingops._common._models import OperationResult
from charmlibs.rollingops._common._utils import (
    ETCD_FAILED_HOOK_NAME,
    dispatch_etcd_failed,
    dispatch_lock_granted,
    setup_logging,
)
from charmlibs.rollingops._etcd._etcd import (
    EtcdLease,
    EtcdLock,
    WorkerOperationStore,
)
from charmlibs.rollingops._etcd._models import RollingOpsKeys
from charmlibs.rollingops._etcd._worker import ETCD_LOG_FILENAME

logger = logging.getLogger(__name__)

INITIAL_SLEEP = 10  # Delay before the worker begins processing.
LOCK_ACQUIRE_SLEEP = 15  # Delay between etcd lock acquisition attempts.
NEXT_OP_SLEEP = 30  # Delay between queue polls when idle.


class RollingOpsEtcdInconsistencyError(Exception):
    """Raised when unexpected or inconsistent etcd operation state is found."""


def main():
    """Run the etcd rolling-ops worker loop.

    This worker is responsible for processing the current unit's
    etcd-backed operation queue. It waits for pending work, acquires the
    etcd lock, claims the next operation, dispatches the lock-granted
    hook, and then waits for the operation result to be written back.

    Processing behavior depends on the final operation result:

    - `RETRY_HOLD`: requeue the operation immediately and keep the lock
    - `RETRY_RELEASE`: requeue the operation and release the lock
    - any other result: remove the completed operation and release the lock

    If the worker detects invalid etcd queue state or encounters an
    unrecoverable error, it dispatches the ETCD_FAILED_HOOK_NAME
    hook so the charm can fall back to peer-based processing.

    The worker always attempts to revoke its lease and release the lock
    before exiting.
    """
    parser = argparse.ArgumentParser(description='RollingOps etcd worker')
    parser.add_argument(
        '--base-dir',
        type=pathops.LocalPath,
        required=True,
        help='Base directory used to store all rollingops files.',
    )
    parser.add_argument(
        '--unit-name',
        type=str,
        required=True,
        help='Juju unit name (e.g. app/0)',
    )
    parser.add_argument(
        '--charm-dir',
        type=str,
        required=True,
        help='Path to the charm directory',
    )

    parser.add_argument(
        '--owner',
        type=str,
        required=True,
        help='Unique owner identifier for the unit',
    )
    parser.add_argument(
        '--cluster-id',
        type=str,
        required=True,
        help='Cluster identifier',
    )
    args = parser.parse_args()

    base_dir = args.base_dir
    setup_logging(
        base_dir=base_dir,
        log_filename=ETCD_LOG_FILENAME,
        unit_name=args.unit_name,
        owner=args.owner,
        cluster_id=args.cluster_id,
    )
    logger.info('Starting worker.')

    time.sleep(INITIAL_SLEEP)

    keys = RollingOpsKeys.for_owner(args.cluster_id, args.owner)
    lock = EtcdLock(keys.lock_key, args.owner, base_dir)
    lease = EtcdLease(base_dir)
    operations = WorkerOperationStore(keys, args.owner, base_dir)

    try:
        while True:
            if operations.has_inprogress() or operations.has_completed():
                raise RollingOpsEtcdInconsistencyError('Invalid operations found in etcd queues.')

            if not operations.has_pending():
                time.sleep(NEXT_OP_SLEEP)
                continue

            logger.info('Operation found in the pending queue.')

            if not lock.is_held():
                if lease.id is None:
                    lease.grant()

                if lease.id is None:
                    raise RollingOpsEtcdInconsistencyError('Invalid lease ID found.')

                logger.info('Try to get lock using lease %s.', lease.id)
                while not lock.try_acquire(lease.id):
                    time.sleep(LOCK_ACQUIRE_SLEEP)
                    continue
            logger.info('Lock granted using lease %s.', lease.id)

            op_id = operations.claim_next()

            dispatch_lock_granted(args.unit_name, args.charm_dir)

            logger.info('Waiting for operation %s to be finished.', op_id)
            operation = operations.wait_until_completed()

            logger.info('Operation %s completed with %s', operation.op_id, operation.result)
            match operation.result:
                case OperationResult.RETRY_HOLD:
                    operations.requeue_completed()
                    continue

                case OperationResult.RETRY_RELEASE:
                    operations.requeue_completed()

                case _:
                    operations.delete_completed()

            lease_id = lease.id
            lease.revoke()
            lock.release()
            logger.info('Lease %s revoked and lock released.', lease_id)
            time.sleep(NEXT_OP_SLEEP)

    except Exception as e:
        logger.exception('Fatal etcd worker error: %s', e)

        try:
            dispatch_etcd_failed(args.unit_name, args.charm_dir)
        except Exception:
            logger.exception('Failed to dispatch %s hook.', ETCD_FAILED_HOOK_NAME)

    finally:
        lease_id = lease.id
        try:
            lease.revoke()
            logger.info('Lease %s revoked.', lease_id)
        except Exception:
            logger.exception('Failed to revoke lease %s during worker shutdown.', lease_id)

        try:
            lock.release()
            logger.info('Lock released.')
        except Exception:
            logger.exception('Failed to release lock during worker shutdown.')

        logger.info('Exit.')


if __name__ == '__main__':
    main()
