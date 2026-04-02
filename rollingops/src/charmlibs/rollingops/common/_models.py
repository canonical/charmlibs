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

"""etcd rolling ops models."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
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


def now_timestamp_str() -> str:
    """UTC timestamp as a string using ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def parse_timestamp(timestamp: str) -> datetime | None:
    """Parse timestamp string. Return None on errors to avoid selecting invalid timestamps."""
    try:
        return datetime.fromisoformat(timestamp)
    except Exception:
        return None


class OperationResult(StrEnum):
    """Callback return values."""

    RELEASE = 'release'
    RETRY_RELEASE = 'retry-release'
    RETRY_HOLD = 'retry-hold'
