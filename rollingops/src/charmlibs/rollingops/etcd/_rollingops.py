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

from charmlibs.rollingops.common._models import OperationResult
from charmlibs.rollingops.common._utils import dispatch_hook, dispatch_lock_granted, setup_logging
from charmlibs.rollingops.etcd._etcd import (
    EtcdLease,
    EtcdLock,
    WorkerOperationStore,
)
from charmlibs.rollingops.etcd._models import RollingOpsKeys

logger = logging.getLogger(__name__)

INITIAL_SLEEP = 10  # Delay before the worker begins processing.
LOCK_ACQUIRE_SLEEP = 15  # Delay between etcd lock acquisition attempts.
NEXT_OP_SLEEP = 30  # Delay between queue polls when idle.


class RollingOpsEtcdInconsistencyError(Exception):
    """Raised when unexpected or inconsistent etcd operation state is found."""


def _dispatch_etcd_failed(unit_name: str, charm_dir: str) -> None:
    """Dispatch the fatal etcd-worker failure hook.

    This notifies the charm that the etcd worker encountered an
    unrecoverable error so that higher-level logic can fall back to the
    peer backend.

    Args:
        unit_name: Name of the unit dispatching the hook.
        charm_dir: Path to the charm root directory.
    """
    hook_name = 'rollingops_etcd_failed'
    dispatch_hook(unit_name, charm_dir, hook_name)


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
    unrecoverable error, it dispatches the `rollingops_etcd_failed`
    hook so the charm can fall back to peer-based processing.

    The worker always attempts to revoke its lease and release the lock
    before exiting.
    """
    setup_logging('/var/log/etcd_rollingops_worker.log')

    parser = argparse.ArgumentParser()
    parser.add_argument('--unit-name', required=True)
    parser.add_argument('--charm-dir', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--cluster-id', required=True)
    args = parser.parse_args()

    logger.info(
        'Worker starting (unit=%s owner=%s cluster=%s)',
        args.unit_name,
        args.owner,
        args.cluster_id,
    )

    time.sleep(INITIAL_SLEEP)

    keys = RollingOpsKeys.for_owner(args.cluster_id, args.owner)
    lock = EtcdLock(keys.lock_key, args.owner)
    lease = EtcdLease()
    operations = WorkerOperationStore(keys, args.owner)

    try:
        while True:
            if operations.has_inprogress() or operations.has_completed():
                raise RollingOpsEtcdInconsistencyError('Invalid operations found in etcd queues.')

            if not operations.has_pending():
                time.sleep(NEXT_OP_SLEEP)
                continue

            if not lock.is_held():
                if lease.id is None:
                    lease.grant()

                logger.info('Try to get lock.')
                if not lock.try_acquire(lease.id):  # pyright: ignore[reportArgumentType]
                    time.sleep(LOCK_ACQUIRE_SLEEP)
                    continue
                logger.info('Lock granted.')

            operations.claim_next()

            dispatch_lock_granted(args.unit_name, args.charm_dir)

            logger.info('Waiting for operation to be finished.')
            operation = operations.wait_until_completed()

            logger.info('Operation %s completed with %s', operation.callback_id, operation.result)
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
            logger.info('Lease revoked and lock released.')
            time.sleep(NEXT_OP_SLEEP)

    except Exception as e:
        logger.exception('Fatal etcd worker error: %s', e)

        try:
            _dispatch_etcd_failed(args.unit_name, args.charm_dir)
        except Exception:
            logger.exception('Failed to dispatch rollingops_etcd_failed hook.')

    finally:
        try:
            lease.revoke()
        except Exception:
            logger.exception('Failed to revoke lease during worker shutdown.')

        try:
            lock.release()
        except Exception:
            logger.exception('Failed to release lock during worker shutdown.')

        logger.info('Exit.')


if __name__ == '__main__':
    main()
