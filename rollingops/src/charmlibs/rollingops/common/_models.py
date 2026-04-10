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

"""Rolling ops common models."""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ops import Model, Unit

from charmlibs.rollingops.common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsNoRelationError,
)
from charmlibs.rollingops.common._utils import datetime_to_str, now_timestamp, parse_timestamp

logger = logging.getLogger(__name__)


class OperationResult(StrEnum):
    """Callback return values."""

    RELEASE = 'release'
    RETRY_RELEASE = 'retry-release'
    RETRY_HOLD = 'retry-hold'


class ProcessingBackend(StrEnum):
    """Backend responsible for processing a unit's queue."""

    PEER = 'peer'
    ETCD = 'etcd'


class RunWithLockStatus(StrEnum):
    NOT_GRANTED = 'not_granted'
    NO_OPERATION = 'no_operation'
    MISSING_CALLBACK = 'missing_callback'
    EXECUTED = 'executed'


class RollingOpsStatus(StrEnum):
    INVALID = 'invalid'
    WAITING = 'waiting'
    GRANTED = 'granted'
    IDLE = 'idle'


@dataclass
class RunWithLockOutcome:
    """Outcome of attempting to execute the current operation under a lock."""

    status: RunWithLockStatus
    op_id: str | None = None
    result: OperationResult | None = None

    @property
    def executed(self) -> bool:
        return self.status == RunWithLockStatus.EXECUTED


@dataclass
class BackendState:
    """Unit-scoped backend ownership and recovery state."""

    processing_backend: str = ProcessingBackend.PEER
    etcd_cleanup_needed: str = 'false'

    @property
    def cleanup_needed(self) -> bool:
        """Return whether stale etcd state must be cleaned before reuse."""
        return self.etcd_cleanup_needed == 'true'

    @cleanup_needed.setter
    def cleanup_needed(self, value: bool) -> None:
        """Persist whether stale etcd state cleanup is required."""
        self.etcd_cleanup_needed = 'true' if value else 'false'

    @property
    def backend(self) -> ProcessingBackend:
        """Return which backend owns execution for this unit's queue."""
        if not self.processing_backend:
            return ProcessingBackend.PEER
        return ProcessingBackend(self.processing_backend)

    @backend.setter
    def backend(self, value: ProcessingBackend) -> None:
        """Persist the backend owner."""
        self.processing_backend = value


class UnitBackendState:
    """Manage backend ownership and fallback state for one unit queue."""

    def __init__(self, model: Model, relation_name: str, unit: Unit):
        relation = model.get_relation(relation_name)
        if relation is None:
            raise RollingOpsNoRelationError()

        self._relation = relation
        self.unit = unit

    def _load(self) -> BackendState:
        return self._relation.load(BackendState, self.unit, decoder=lambda s: s)

    def _save(self, data: BackendState) -> None:
        self._relation.save(data, self.unit, encoder=str)

    @property
    def backend(self) -> ProcessingBackend:
        """Return which backend owns execution for this unit's queue."""
        return self._load().backend

    @property
    def cleanup_needed(self) -> bool:
        """Return whether etcd cleanup is required before etcd can be reused."""
        return self._load().cleanup_needed

    def fallback_to_peer(self) -> None:
        """Switch this unit's queue to peer processing and mark etcd cleanup needed."""
        data = self._load()
        data.backend = ProcessingBackend.PEER
        data.cleanup_needed = True
        self._save(data)

    def clear_fallback(self) -> None:
        """Clear the etcd cleanup-needed flag and set the backend to ETCD."""
        data = self._load()
        data.backend = ProcessingBackend.ETCD
        data.cleanup_needed = False
        self._save(data)

    def is_peer_managed(self) -> bool:
        """Return whether the peer backend should process this unit's queue."""
        return self.backend == ProcessingBackend.PEER

    def is_etcd_managed(self) -> bool:
        """Return whether the etcd backend should process this unit's queue."""
        return self.backend == ProcessingBackend.ETCD


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
            'requested_at': datetime_to_str(self.requested_at),
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
        return f'{datetime_to_str(self.requested_at)}-{self.callback_id}'

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


class OperationQueue:
    """In-memory FIFO queue of Operations with encode/decode helpers for storing in a databag."""

    def __init__(self, operations: list[Operation] | None = None):
        self.operations: list[Operation] = list(operations or [])

    def __len__(self) -> int:
        """Return the number of operations in the queue."""
        return len(self.operations)

    @property
    def empty(self) -> bool:
        """Return True if there are no queued operations."""
        return not self.operations

    def peek(self) -> Operation | None:
        """Return the first operation in the queue if it exists."""
        return self.operations[0] if self.operations else None

    def _peek_last(self) -> Operation | None:
        """Return the last operation in the queue if it exists."""
        return self.operations[-1] if self.operations else None

    def dequeue(self) -> Operation | None:
        """Drop the first operation in the queue if it exists and return it."""
        return self.operations.pop(0) if self.operations else None

    def increase_attempt(self) -> None:
        """Increment the attempt counter for the head operation and persist it."""
        if self.empty:
            return
        self.operations[0].increase_attempt()

    def enqueue(self, operation: Operation) -> None:
        """Append operation only if it is not equal to the tail operation."""
        last_operation = self._peek_last()
        if last_operation is not None and last_operation == operation:
            return
        self.operations.append(operation)

    def to_string(self) -> str:
        """Encode entire queue to a single string."""
        items = [op.to_string() for op in self.operations]
        return json.dumps(items, separators=(',', ':'))

    @classmethod
    def from_string(cls, data: str) -> 'OperationQueue':
        """Decode queue from a string.

        Raises:
            RollingOpsDecodingError: if data cannot be deserialized.
        """
        if not data:
            return cls()

        try:
            items = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(
                'Failed to deserialize data to create an OperationQueue from %s: %s', data, e
            )
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an OperationQueue.'
            ) from e
        if not isinstance(items, list) or not all(isinstance(s, str) for s in items):  # type: ignore[reportUnknownVariableType]
            raise RollingOpsDecodingError(
                'OperationQueue string must decode to a JSON list of strings.'
            )

        operations = [Operation.from_string(s) for s in items]  # type: ignore[reportUnknownVariableType]
        return cls(operations)


@dataclass
class RollingOpsState:
    status: RollingOpsStatus
    processing_backend: ProcessingBackend | None
    operations: OperationQueue


class SyncLockBackend(ABC):
    @abstractmethod
    def acquire(self, timeout: int) -> None:
        pass

    @abstractmethod
    def release(self) -> None:
        pass
