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
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from charmlibs.rollingops.peer_models import (
    Operation,
    OperationQueue,
    RollingOpsDecodingError,
)


def _decode_queue_string(queue_str: str) -> list[dict[str, str]]:
    """Helper: decode OperationQueue.to_string() -> list of dicts."""
    items = json.loads(queue_str)
    assert isinstance(items, list)
    return [json.loads(s) for s in items]  # type: ignore[reportUnknownArgumentType]


def test_operation_create_sets_fields():
    op = Operation.create('restart', {'b': 2, 'a': 1}, max_retry=3)

    assert op.kwargs == {'b': 2, 'a': 1}
    assert op.callback_id == 'restart'
    assert op.max_retry == 3
    assert isinstance(op.requested_at, datetime)


def test_operation_to_string_contains_string_values_only():
    ts = datetime(2026, 2, 23, 12, 0, 0, 123456, tzinfo=UTC)
    op = Operation(
        callback_id='cb', kwargs={'b': 2, 'a': 1}, requested_at=ts, max_retry=None, attempt=0
    )

    s = op.to_string()
    obj = json.loads(s)

    assert obj['callback_id'] == 'cb'
    assert obj['kwargs'] == '{"a":1,"b":2}'
    assert obj['requested_at'] == ts.isoformat()
    assert obj.get('max_retry', '') == ''


def test_operation_to_string_contains_string_values_only_zero_max_retry():
    ts = datetime(2026, 2, 23, 12, 0, 0, 123456, tzinfo=UTC)
    op = Operation(
        callback_id='cb', kwargs={'b': 2, 'a': 1}, requested_at=ts, max_retry=0, attempt=0
    )

    s = op.to_string()
    obj = json.loads(s)

    assert obj['callback_id'] == 'cb'
    assert obj['kwargs'] == '{"a":1,"b":2}'
    assert obj['requested_at'] == ts.isoformat()
    assert obj.get('max_retry', '') == '0'


def test_operation_is_max_retry_reached_on_zero_max_retry():
    op = Operation.create('restart', {'a': 1, 'b': 2}, max_retry=0)
    assert not op.is_max_retry_reached()
    op.increase_attempt()
    assert op.is_max_retry_reached()


def test_operation_equality_and_hash_ignore_timestamp_and_max_retry():
    # Equality only depends on (callback_id, kwargs)
    op1 = Operation.create('restart', {'a': 1, 'b': 2}, max_retry=0)
    op2 = Operation.create('restart', {'b': 2, 'a': 1}, max_retry=999)

    assert op1 == op2
    assert hash(op1) == hash(op2)

    op3 = Operation.create('restart', {'a': 2}, max_retry=0)
    assert op1 != op3


def test_operation_equality_and_hash_empty_arguments():
    # Equality only depends on (callback_id, kwargs)
    op1 = Operation.create('restart', {}, max_retry=0)
    op2 = Operation.create('restart', {}, max_retry=999)

    assert op1 == op2
    assert hash(op1) == hash(op2)

    op3 = Operation.create('restart', {'a': 2}, max_retry=0)
    assert op1 != op3


def test_operation_to_string_and_from_string():
    ts = datetime(2026, 2, 23, 12, 0, 0, 0, tzinfo=UTC)
    op1 = Operation(
        callback_id='cb', kwargs={'x': 1, 'y': 'z'}, requested_at=ts, max_retry=5, attempt=0
    )

    s = op1.to_string()
    op2 = Operation.from_string(s)

    assert op2.callback_id == op1.callback_id
    assert op2.kwargs == op1.kwargs
    assert op2.requested_at == op1.requested_at
    assert op2.max_retry == op1.max_retry
    assert op2.attempt == op1.attempt


def test_operation_from_string_valid_payload():
    requested_at = datetime(2026, 3, 12, 10, 30, 45, 123456, tzinfo=UTC)
    payload = json.dumps({
        'callback_id': 'cb-123',
        'kwargs': json.dumps({'b': 2, 'a': 'x'}),
        'requested_at': requested_at.isoformat(),
        'max_retry': '5',
        'attempt': '2',
    })

    op = Operation.from_string(payload)

    assert op is not None
    assert op.callback_id == 'cb-123'
    assert op.kwargs == {'b': 2, 'a': 'x'}
    assert op.requested_at == requested_at
    assert op.max_retry == 5
    assert op.attempt == 2


def test_from_string_valid_payload_with_empty_kwargs_and_no_max_retry():
    requested_at = datetime(2026, 3, 12, 10, 30, 45, 123456, tzinfo=UTC)
    payload = json.dumps({
        'callback_id': 'cb-123',
        'kwargs': '',
        'requested_at': requested_at.isoformat(),
        'max_retry': '',
        'attempt': '0',
    })

    op = Operation.from_string(payload)

    assert op is not None
    assert op.callback_id == 'cb-123'
    assert op.kwargs == {}
    assert op.requested_at == requested_at
    assert op.max_retry is None
    assert op.attempt == 0


def test_from_string_valid_payload_with_empty_kwargs_and_0_max_retry():
    requested_at = datetime(2026, 3, 12, 10, 30, 45, 123456, tzinfo=UTC)
    payload = json.dumps({
        'callback_id': 'cb-123',
        'kwargs': '{}',
        'requested_at': requested_at.isoformat(),
        'max_retry': '0',
        'attempt': '0',
    })

    op = Operation.from_string(payload)

    assert op is not None
    assert op.callback_id == 'cb-123'
    assert op.kwargs == {}
    assert op.requested_at == requested_at
    assert op.max_retry == 0
    assert op.attempt == 0


@pytest.mark.parametrize(
    'payload',
    [
        '{not valid json',
        json.dumps(  # invalid requested_at
            {
                'callback_id': 'cb-123',
                'kwargs': json.dumps({'x': 1}),
                'requested_at': 'bad-ts',
                'max_retry': '3',
                'attempt': '1',
            }
        ),
        json.dumps(  # invalid kwargs
            {
                'callback_id': 'cb-123',
                'kwargs': '{bad kwargs json',
                'requested_at': datetime.now(UTC).isoformat(),
                'max_retry': '3',
                'attempt': '1',
            }
        ),
        json.dumps(  # missing callback_id
            {
                'kwargs': json.dumps({'x': 1}),
                'requested_at': datetime.now(UTC).isoformat(),
                'max_retry': '3',
                'attempt': '1',
            }
        ),
        json.dumps(  # invalid kwargs
            {
                'callback_id': 'cb-123',
                'kwargs': '[]',
                'requested_at': datetime.now(UTC).isoformat(),
                'max_retry': '3',
                'attempt': '1',
            }
        ),
        json.dumps(  # missing requested_at
            {
                'callback_id': 'cb-123',
                'kwargs': '{}',
                'requested_at': '',
                'max_retry': '3',
                'attempt': '1',
            }
        ),
    ],
)
def test_operation_from_string_invalid_inputs_return_none(payload: Any):
    with pytest.raises(RollingOpsDecodingError, match='Failed to deserialize'):
        Operation.from_string(payload)


def test_queue_empty_behaviour():
    q = OperationQueue()

    assert len(q) == 0
    assert q.empty is True
    assert q.peek() is None
    assert q.dequeue() is None

    assert json.loads(q.to_string()) == []


def test_queue_enqueue_and_fifo_order():
    q = OperationQueue()
    q.enqueue_lock_request('a', {'i': 1})
    q.enqueue_lock_request('b', {'i': 2})

    assert len(q) == 2
    op = q.peek()
    assert op is not None
    assert op.callback_id == 'a'

    first = q.dequeue()
    assert first is not None
    assert first.callback_id == 'a'
    assert len(q) == 1
    op = q.peek()
    assert op is not None
    assert op.callback_id == 'b'

    second = q.dequeue()
    assert second is not None
    assert second.callback_id == 'b'
    assert q.empty is True


def test_queue_deduplicates_only_against_last_item():
    q = OperationQueue()

    q.enqueue_lock_request('restart', {'x': 1})
    assert len(q) == 1

    q.enqueue_lock_request('restart', {'x': 1})
    assert len(q) == 1

    q.enqueue_lock_request('restart', {'x': 2})
    assert len(q) == 2

    q.enqueue_lock_request('restart', {'x': 1})
    assert len(q) == 3


def test_queue_to_string_and_from_string():
    q1 = OperationQueue()
    q1.enqueue_lock_request('a', {'x': 1}, max_retry=5)
    q1.enqueue_lock_request('b', {'y': 'z'}, max_retry=None)

    encoded = q1.to_string()
    q2 = OperationQueue.from_string(encoded)

    assert len(q2) == 2
    op = q2.peek()
    assert op is not None
    assert op.callback_id == 'a'

    op = q2.dequeue()
    assert op is not None
    assert op.callback_id == 'a'

    op = q2.dequeue()
    assert op is not None
    assert op.callback_id == 'b'
    assert q2.empty


def test_queue_from_string_empty_string_is_empty_queue():
    q = OperationQueue.from_string('')
    assert q.empty
    assert q.peek() is None


def test_queue_from_string_rejects_non_list_json():
    with pytest.raises(RollingOpsDecodingError, match='OperationQueue string'):
        OperationQueue.from_string(json.dumps({'not': 'a list'}))


def test_queue_from_string_rejects_invalid_jason():
    with pytest.raises(RollingOpsDecodingError, match='Failed to deserialize data'):
        OperationQueue.from_string('{invalid')


def test_queue_encoding_is_list_of_operation_strings():
    q = OperationQueue()
    q.enqueue_lock_request('a', {'x': 1})
    s = q.to_string()

    decoded = json.loads(s)
    assert isinstance(decoded, list)
    assert len(decoded) == 1  # type: ignore[reportUnknownArgumentType]
    assert isinstance(decoded[0], str)

    op_dicts = _decode_queue_string(s)
    assert op_dicts[0]['callback_id'] == 'a'
    assert op_dicts[0]['kwargs'] == '{"x":1}'
    assert op_dicts[0].get('max_retry', '') == ''
    assert 'requested_at' in op_dicts[0]
