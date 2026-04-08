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
import subprocess
import time
from logging.handlers import RotatingFileHandler

from charmlibs.rollingops.common._models import OperationResult
from charmlibs.rollingops.etcd._etcd import (
    EtcdLease,
    EtcdLock,
    WorkerOperationStore,
)
from charmlibs.rollingops.etcd._models import RollingOpsKeys

logger = logging.getLogger(__name__)


def setup_logging(log_file: str) -> None:
    handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(process)d] %(name)s: %(message)s'
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _dispatch_hook(unit_name: str, charm_dir: str, hook_name: str) -> None:
    """Dispatch a custom Juju hook."""
    run_cmd = '/usr/bin/juju-exec'
    dispatch_sub_cmd = f'JUJU_DISPATCH_PATH=hooks/{hook_name} {charm_dir}/dispatch'
    res = subprocess.run([run_cmd, '-u', unit_name, dispatch_sub_cmd], check=False)
    res.check_returncode()
    logger.info('%s hook dispatched.', hook_name)


def _dispatch_lock_granted(unit_name: str, charm_dir: str) -> None:
    """Dispatch the rollingops_lock_granted hook."""
    hook_name = 'rollingops_lock_granted'
    _dispatch_hook(unit_name, charm_dir, hook_name)


def _dispatch_etcd_failed(unit_name: str, charm_dir: str) -> None:
    """Dispatch the rollingops_etcd_failed hook."""
    hook_name = 'rollingops_etcd_failed'
    _dispatch_hook(unit_name, charm_dir, hook_name)


def main():
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

    lock_lease_ttl = 60
    acquire_retry_sleep = 15

    time.sleep(10)

    keys = RollingOpsKeys.for_owner(args.cluster_id, args.owner)
    lock = EtcdLock(keys.lock_key, args.owner)
    lease = EtcdLease()
    operations = WorkerOperationStore(keys, args.owner)

    try:
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

                logger.info('Try to get lock.')
                if not lock.try_acquire(lease_id):
                    time.sleep(acquire_retry_sleep)
                    continue

                logger.info('Lock granted.')

            if not operations.claim_next():
                time.sleep(acquire_retry_sleep)
                continue

            _dispatch_lock_granted(args.unit_name, args.charm_dir)

            logger.info('Waiting for operation to be finished.')
            operations.wait_until_completed()
            operation = operations.peek_completed()
            if operation is None:
                logger.info('Completed queue watch returned no operation.')
                time.sleep(acquire_retry_sleep)
                continue

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
            logger.info('Lease revoked.')
            lock.release()
            logger.info('Lock released.')

            if not operations.has_pending():
                logger.info('No more operations in the queue.')
                break

            time.sleep(acquire_retry_sleep)
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
