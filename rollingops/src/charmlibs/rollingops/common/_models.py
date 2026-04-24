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
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from ops import Model, Unit
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_serializer,
    field_validator,
)

from charmlibs.rollingops.common._exceptions import (
    RollingOpsDecodingError,
    RollingOpsNoRelationError,
)
from charmlibs.rollingops.common._utils import datetime_to_str, now_timestamp, parse_timestamp

logger = logging.getLogger(__name__)


class OperationResult(StrEnum):
    """Result values returned by rolling-ops callbacks on async locks.

    These values control how the rolling-ops manager updates the operation
    state and whether the distributed lock is released or retained.

    - RELEASE:
        The operation completed successfully and no retry is required.
        The lock is released and the next unit may be scheduled.

    - RETRY_RELEASE:
        The operation failed or timed out and should be retried later.
        The operation is re-queued and the lock is released so that
        other units may proceed before this operation is retried.

    - RETRY_HOLD:
        The operation failed or timed out and should be retried immediately.
        The operation is re-queued and the lock is kept by the current
        unit, allowing it to retry immediately.
    """

    RELEASE = 'release'
    RETRY_RELEASE = 'retry-release'
    RETRY_HOLD = 'retry-hold'


class ProcessingBackend(StrEnum):
    """Backend responsible for processing a unit's queue."""

    PEER = 'peer'
    ETCD = 'etcd'


class RunWithLockStatus(StrEnum):
    """Status of an attempt to execute an operation under a distributed lock.

    These values describe what happened when a unit tried to run an
    operation while interacting with the lock.
    """

    NOT_GRANTED = 'not_granted'
    NO_OPERATION = 'no_operation'
    MISSING_CALLBACK = 'missing_callback'
    EXECUTED = 'executed'
    EXECUTED_NOT_COMMITTED = 'executed_not_committed'


class RollingOpsStatus(StrEnum):
    """High-level rolling-ops status for a unit.

    It reflects whether the unit is currently executing work, waiting
    for execution, idle, or unable to participate.

    States:

    - NOT_READY:
        Rolling-ops cannot be used on this unit. This typically occurs when
        required relations are missing or the selected backend is not reachable.
        * peer backend: peer relation does not exist
        * etcd backend: peer or etcd relation missing, or etcd not reachable

    - WAITING: The unit has pending operations but does not currently hold the lock.

    - GRANTED: The unit currently holds the lock and may execute operations.

    - IDLE: The unit has no pending operations and is not holding the lock.
    """

    NOT_READY = 'not-ready'
    WAITING = 'waiting'
    GRANTED = 'granted'
    IDLE = 'idle'


@dataclass(frozen=True)
class RunWithLockOutcome:
    """Result of attempting to execute an operation under a distributed lock.

    This object captures both whether an operation was executed and, if so,
    the identity and result of that operation. It is used to propagate
    execution outcomes across backends (e.g. etcd → peer mirroring).
    """

    status: RunWithLockStatus
    op_id: str | None = None
    result: OperationResult | None = None


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

        self._backend_state = self._relation.load(BackendState, self.unit, decoder=lambda s: s)

    def _save(self, data: BackendState) -> None:
        self._relation.save(data, self.unit, encoder=str)

    @property
    def backend(self) -> ProcessingBackend:
        """Return which backend owns execution for this unit's queue."""
        return self._backend_state.backend

    @property
    def cleanup_needed(self) -> bool:
        """Return whether etcd cleanup is required before etcd can be reused."""
        return self._backend_state.cleanup_needed

    def fallback_to_peer(self) -> None:
        """Switch this unit's queue to peer processing and mark etcd cleanup needed."""
        self._backend_state.backend = ProcessingBackend.PEER
        self._backend_state.cleanup_needed = True
        self._save(self._backend_state)

    def clear_fallback(self) -> None:
        """Clear the etcd cleanup-needed flag and set the backend to ETCD."""
        self._backend_state.backend = ProcessingBackend.ETCD
        self._backend_state.cleanup_needed = False
        self._save(self._backend_state)

    def is_peer_managed(self) -> bool:
        """Return whether the peer backend should process this unit's queue."""
        return self.backend == ProcessingBackend.PEER

    def is_etcd_managed(self) -> bool:
        """Return whether the etcd backend should process this unit's queue."""
        return self.backend == ProcessingBackend.ETCD


class Operation(BaseModel):
    """A single queued operation."""

    model_config = ConfigDict(use_enum_values=True)

    callback_id: str
    requested_at: datetime
    max_retry: int | None = None
    attempt: int = 0
    result: OperationResult | None = None
    kwargs: dict[str, Any] = Field(default_factory=dict)

    @field_validator('callback_id')
    @classmethod
    def validate_callback_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('callback_id must be a non-empty string')
        return value

    @field_validator('kwargs')
    @classmethod
    def validate_kwargs(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value)
        except TypeError as e:
            raise ValueError(f'kwargs must be JSON-serializable: {e}') from e
        return value

    @field_serializer('kwargs')
    def serialize_kwargs(self, value: dict[str, Any]) -> dict[str, Any]:
        """Ensure deterministic ordering of kwargs."""
        return dict(sorted(value.items()))

    @field_validator('max_retry')
    @classmethod
    def validate_max_retry(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError('max_retry must be >= 0')
        return value

    @field_validator('attempt')
    @classmethod
    def validate_attempt(cls, value: int) -> int:
        if value < 0:
            raise ValueError('attempt must be >= 0')
        return value

    @field_validator('requested_at', mode='before')
    @classmethod
    def validate_requested_at(cls, value: Any) -> Any:
        if isinstance(value, str):
            return parse_timestamp(value)
        return value

    @field_serializer('requested_at')
    def serialize_requested_at(self, value: datetime) -> str:
        return datetime_to_str(value)

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

    def to_string(self) -> str:
        """Serialize to a single JSON object string."""
        return self.model_dump_json()

    @classmethod
    def from_string(cls, data: str) -> 'Operation':
        """Deserialize from a JSON string."""
        try:
            return cls.model_validate_json(data)
        except Exception as e:
            logger.error('Failed to deserialize Operation from %s: %s', data, e)
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an Operation'
            ) from e

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
        """Mark the operation to be retried later, releasing the lock.

        If the maximum retry count is reached, the operation is marked as
        ``RELEASE`` and will not be retried further.
        """
        self.increase_attempt()
        if self.is_max_retry_reached():
            logger.warning('Operation max retry reached. Dropping.')
            self.result = OperationResult.RELEASE
        else:
            self.result = OperationResult.RETRY_RELEASE

    def retry_hold(self) -> None:
        """Mark the operation to be retried immediately, retaining the lock.

        If the maximum retry count is reached, the operation is marked as
        ``RELEASE`` and will not be retried further.
        """
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


class OperationQueue(RootModel[list[Operation]]):
    """In-memory FIFO queue of Operations with encode/decode helpers for storing in a databag."""

    def __init__(self, operations: list[Operation] | None = None) -> None:
        super().__init__(root=operations or [])  # pyright: ignore[reportUnknownMemberType]

    @property
    def operations(self) -> list[Operation]:
        """Return the underlying list of operations."""
        return self.root

    def __len__(self) -> int:
        """Return the number of operations in the queue."""
        return len(self.root)

    @property
    def empty(self) -> bool:
        """Return True if there are no queued operations."""
        return not self.root

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
        """Encode entire queue to a single JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_string(cls, data: str) -> 'OperationQueue':
        """Decode a queue from a JSON string.

        Args:
            data: Serialized queue as a JSON array of operation objects.

        Returns:
            The decoded operation queue.

        Raises:
            RollingOpsDecodingError: If the queue cannot be deserialized.
        """
        if not data:
            return cls([])

        try:
            return cls.model_validate_json(data)
        except Exception as e:
            logger.error(
                'Failed to deserialize data to create an OperationQueue from %s: %s',
                data,
                e,
            )
            raise RollingOpsDecodingError(
                'Failed to deserialize data to create an OperationQueue.'
            ) from e


@dataclass(frozen=True)
class RollingOpsState:
    """Snapshot of the rolling-ops state for a unit.

    This object provides a view of the rolling-ops system from the perspective
    of a single unit.

    This state is intended for decision-making in charm logic

    The `processing_backend` reflects the backend currently selected
        for execution. It may change dynamically (e.g. fallback from etcd
        to peer).
    The `operations` queue always reflects the peer-backed state, which
        acts as the source of truth and fallback mechanism.
    When `status` is NOT_READY, the unit cannot currently participate
        in rolling operations due to missing relations or backend failures.

    status: High-level rolling-ops status for the unit.
    processing_backend: Backend currently responsible for executing operations (e.g. ETCD or PEER).
    operations: The unit's operation queue.
    """

    status: RollingOpsStatus
    processing_backend: ProcessingBackend
    operations: OperationQueue


class SyncLockBackend(ABC):
    """Interface for synchronous lock backends.

    Implementations provide a mechanism to acquire and release a lock
    protecting a critical section. These backends are used by the
    RollingOpsManager to coordinate synchronous operations within a
    single unit when etcd is not available.
    """

    @abstractmethod
    def acquire(self, timeout: int | None) -> None:
        """Acquire the lock, blocking until it is granted or timeout expires.

        Args:
            timeout: Maximum time in seconds to wait for the lock.
                None means wait indefinitely.

        Raises:
            TimeoutError: If the lock could not be acquired within the timeout.
        """
        raise NotImplementedError

    @abstractmethod
    def release(self) -> None:
        """Release the lock.

        Implementations must ensure that only the lock owner can release
        the lock and that any associated resources are cleaned up.
        """
        raise NotImplementedError
