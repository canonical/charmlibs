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

"""Rolling ops common functions."""

import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import TypeVar

from ops import pebble
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from charmlibs.pathops import PebbleConnectionError

logger = logging.getLogger(__name__)
T = TypeVar('T')


@retry(
    retry=retry_if_exception_type((PebbleConnectionError, pebble.APIError, pebble.ChangeError)),
    stop=stop_after_attempt(3),
    wait=wait_fixed(10),
    reraise=True,
)
def with_pebble_retry[T](func: Callable[[], T]) -> T:
    return func()


def now_timestamp() -> datetime:
    """UTC timestamp."""
    return datetime.now(UTC)


def parse_timestamp(timestamp: str) -> datetime | None:
    """Parse epoch timestamp string. Return None on errors."""
    try:
        return datetime.fromtimestamp(float(timestamp), tz=UTC)
    except Exception:
        return None


def datetime_to_str(datetime: datetime) -> str:
    return str(datetime.timestamp())


def setup_logging(log_file: str) -> None:
    """Configure logging with file rotation.

    This sets up the root logger to write INFO-level (and above) logs
    to a rotating file handler. Log files are capped at 10 MB each,
    with up to 3 backup files retained.

    This functions is used in the context of the background process.

    Args:
        log_file: Path to the log file where logs should be written.
    """
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


def dispatch_hook(unit_name: str, charm_dir: str, hook_name: str) -> None:
    """Execute a Juju hook on a specific unit via juju-exec.

    This function triggers a charm hook by invoking the charm's `dispatch`
    script with the appropriate JUJU_DISPATCH_PATH environment variable.

    Args:
        unit_name: The Juju unit name (e.g., "app/0") on which to run the hook.
        charm_dir: Filesystem path to the charm directory containing the dispatch script.
        hook_name: Name of the hook to dispatch (without the "hooks/" prefix).

    Raises:
        subprocess.CalledProcessError: If the juju-exec command fails.
    """
    run_cmd = '/usr/bin/juju-exec'
    dispatch_sub_cmd = f'JUJU_DISPATCH_PATH=hooks/{hook_name} {charm_dir}/dispatch'
    res = subprocess.run([run_cmd, '-u', unit_name, dispatch_sub_cmd], check=False)
    res.check_returncode()
    logger.info('%s hook dispatched.', hook_name)


def dispatch_lock_granted(unit_name: str, charm_dir: str) -> None:
    """Dispatch the 'rollingops_lock_granted' hook on a unit.

    Args:
        unit_name: The Juju unit name (e.g., "app/0").
        charm_dir: Filesystem path to the charm directory.

    Raises:
        subprocess.CalledProcessError: If the hook execution fails.
    """
    hook_name = 'rollingops_lock_granted'
    dispatch_hook(unit_name, charm_dir, hook_name)
