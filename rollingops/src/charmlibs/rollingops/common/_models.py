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

"""Rolling ops models."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar

from ops import pebble
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from charmlibs.pathops import PebbleConnectionError
from charmlibs.rollingops.common._exceptions import RollingOpsDecodingError

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


@dataclass
class Operation:
    """A single queued operation."""

    callback_id: str
    requested_at: datetime
    max_retry: int | None
    attempt: int
    result: OperationResult | None
    kwargs: dict[str, Any] = field(default_factory=dict[str, Any])

    @classmethod
    def _validate_fields(
        cls, callback_id: Any, kwargs: Any, requested_at: Any, max_retry: Any, attempt: Any
    ) -> None:
        """Validate the class attributes."""
        if not isinstance(callback_id, str) or not callback_id.strip():
            raise ValueError('callback_id must be a non-empty string')

        if not isinstance(kwargs, dict):
            raise ValueError('kwargs must be a dict')
        try:
            json.dumps(kwargs)
        except TypeError as e:
            raise ValueError(f'kwargs must be JSON-serializable: {e}') from e

        if not isinstance(requested_at, datetime):
            raise ValueError('requested_at must be a datetime')

        if max_retry is not None:
            if not isinstance(max_retry, int):
                raise ValueError('max_retry must be an int')
            if max_retry < 0:
                raise ValueError('max_retry must be >= 0')

        if not isinstance(attempt, int):
            raise ValueError('attempt must be an int')
        if attempt < 0:
            raise ValueError('attempt must be >= 0')

    def __post_init__(self) -> None:
        """Validate the class attributes."""
        self._validate_fields(
            self.callback_id,
            self.kwargs,
            self.requested_at,
            self.max_retry,
            self.attempt,
        )

    @classmethod
    def create(
        cls,
        callback_id: str,
        kwargs: dict[str, Any],
        max_retry: int | None = None,
    ) -> 'Operation':
        """Create a new operation from a callback id and kwargs."""
        return cls(
            callback_id=callback_id,
            kwargs=kwargs,
            requested_at=now_timestamp(),
            max_retry=max_retry,
            attempt=0,
            result=None,
        )

    def _to_dict(self) -> dict[str, str]:
        """Dict form (string-only values)."""
        return {
            'callback_id': self.callback_id,
            'kwargs': self._kwargs_to_json(),
            'requested_at': self.requested_at.isoformat(),
            'max_retry': '' if self.max_retry is None else str(self.max_retry),
            'attempt': str(self.attempt),
            'result': '' if self.result is None else self.result,
        }

    def to_string(self) -> str:
        """Serialize to a string suitable for a Juju databag."""
        return json.dumps(self._to_dict(), separators=(',', ':'))

    def increase_attempt(self) -> None:
        """Increment the attempt counter."""
        self.attempt += 1

    def is_max_retry_reached(self) -> bool:
        """Return True if attempt exceeds max_retry (unless max_retry is None)."""
        if self.max_retry is None:
            return False
        return self.attempt > self.max_retry

    def complete(self) -> None:
        """Mark the operation as completed to indicate the lock should be released."""
        self.increase_attempt()
        self.result = OperationResult.RELEASE

    def retry_release(self) -> None:
        """Mark the operation for retry if it has not reached the max retry."""
        self.increase_attempt()
        if self.is_max_retry_reached():
            logger.warning('Operation max retry reached. Dropping.')
            self.result = OperationResult.RELEASE
        else:
            self.result = OperationResult.RETRY_RELEASE

    def retry_hold(self) -> None:
        """Mark the operation for retry if it has not reached the max retry."""
        self.increase_attempt()
        if self.is_max_retry_reached():
            self.result = OperationResult.RELEASE
            logger.warning('Operation max retry reached. Dropping.')
        else:
            self.result = OperationResult.RETRY_HOLD

    @property
    def op_id(self) -> str:
        """Return the unique identifier for this operation."""
        return f'{self.requested_at.isoformat()}-{self.callback_id}'

    @classmethod
    def from_string(cls, data: str) -> 'Operation':
        """Deserialize from a Juju databag string.

        Raises:
            RollingOpsDecodingError: if data cannot be deserialized.
        """
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error('Failed to deserialize Operation from %s: %s', data, e)
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an Operation'
            ) from e
        return cls.from_dict(obj)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> 'Operation':
        """Create an Operation from its dict (etcd) representation."""
        try:
            return cls(
                callback_id=data['callback_id'],
                requested_at=parse_timestamp(data['requested_at']),  # type: ignore[reportArgumentType]
                max_retry=int(data['max_retry']) if data.get('max_retry') else None,
                attempt=int(data['attempt']),
                kwargs=json.loads(data['kwargs']) if data.get('kwargs') else {},
                result=OperationResult(data['result']) if data.get('result') else None,
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error('Failed to deserialize Operation from %s: %s', data, e)
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an Operation'
            ) from e

    def _kwargs_to_json(self) -> str:
        """Deterministic JSON serialization for kwargs."""
        return json.dumps(self.kwargs, sort_keys=True, separators=(',', ':'))

    def __eq__(self, other: object) -> bool:
        """Equal for the operation."""
        if not isinstance(other, Operation):
            return False
        return self.callback_id == other.callback_id and self.kwargs == other.kwargs

    def __hash__(self) -> int:
        """Hash for the operation."""
        return hash((self.callback_id, self._kwargs_to_json()))
