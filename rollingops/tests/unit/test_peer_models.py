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

import pytest

from charmlibs.rollingops.common._exceptions import RollingOpsDecodingError
from charmlibs.rollingops.common._models import Operation, OperationQueue


def _decode_queue_string(queue_str: str) -> list[dict[str, str]]:
    """Helper: decode OperationQueue.to_string() -> list of dicts."""
    items = json.loads(queue_str)
    assert isinstance(items, list)
    return [json.loads(s) for s in items]  # type: ignore[reportUnknownArgumentType]


def test_queue_empty_behaviour():
    q = OperationQueue()

    assert len(q) == 0
    assert q.empty is True
    assert q.peek() is None
    assert q.dequeue() is None

    assert json.loads(q.to_string()) == []


def test_queue_enqueue_and_fifo_order():
    q = OperationQueue()
    op1 = Operation.create('a', {'x': 2})
    op2 = Operation.create('b', {'i': 2})
    q.enqueue(op1)
    q.enqueue(op2)

    assert len(q) == 2
    op = q.peek()
    assert op is not None
    assert op == op1

    first = q.dequeue()
    assert first is not None
    assert first == op1
    assert len(q) == 1
    op = q.peek()
    assert op is not None
    assert op == op2

    second = q.dequeue()
    assert second is not None
    assert second == op2
    assert q.empty is True


def test_queue_deduplicates_only_against_last_item():
    q = OperationQueue()
    op1 = Operation.create('a', {'x': 2})
    op2 = Operation.create('a', {'x': 2})
    op3 = Operation.create('a', {'x': 4})

    q.enqueue(op1)
    assert len(q) == 1

    q.enqueue(op2)
    assert len(q) == 1

    q.enqueue(op3)
    assert len(q) == 2

    q.enqueue(op2)
    assert len(q) == 3


def test_queue_to_string_and_from_string():
    q1 = OperationQueue()
    op1 = Operation.create('a', {'x': 1}, max_retry=5)
    op2 = Operation.create('b', {'y': 'z'}, max_retry=None)
    q1.enqueue(op1)
    q1.enqueue(op2)

    encoded = q1.to_string()
    q2 = OperationQueue.from_string(encoded)

    assert len(q2) == 2
    op = q2.peek()
    assert op is not None
    assert op == op1

    op = q2.dequeue()
    assert op is not None
    assert op == op1

    op = q2.dequeue()
    assert op is not None
    assert op == op2
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
    op1 = Operation.create('a', {'x': 1})
    q.enqueue(op1)
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
