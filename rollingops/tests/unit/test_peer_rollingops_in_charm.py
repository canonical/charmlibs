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


import logging
from typing import Any

import pytest
from ops.testing import Context, PeerRelation, State
from scenario import RawDataBagContents
from tests.unit.conftest import PeerRollingOpsCharm

from charmlibs.rollingops.common._exceptions import RollingOpsInvalidLockRequestError
from charmlibs.rollingops.common._models import Operation, now_timestamp_str
from charmlibs.rollingops.peer._models import LockIntent, OperationQueue

logger = logging.getLogger(__name__)


def _unit_databag(state: State, peer: PeerRelation) -> RawDataBagContents:
    return state.get_relation(peer.id).local_unit_data


def _app_databag(state: State, peer: PeerRelation) -> RawDataBagContents:
    return state.get_relation(peer.id).local_app_data


def _make_operation_queue(
    callback_id: str, kwargs: dict[str, Any], max_retry: int | None
) -> OperationQueue:
    q = OperationQueue()
    op1 = Operation.create(callback_id=callback_id, kwargs=kwargs, max_retry=max_retry)
    q.enqueue(op1)
    return q


def test_lock_request_enqueues_and_sets_request(
    peer_ctx: Context[PeerRollingOpsCharm],
):
    peer = PeerRelation(endpoint='restart')
    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(
        peer_ctx.on.action('restart', params={'delay': 10}),
        state_in,
    )

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.REQUEST
    assert databag['operations']

    q = OperationQueue.from_string(databag['operations'])
    assert len(q) == 1
    operation = q.peek()
    assert operation is not None
    assert operation.callback_id == '_restart'
    assert operation.kwargs == {'delay': 10}
    assert operation.max_retry is None
    assert operation.requested_at is not None


@pytest.mark.parametrize(
    'max_retry',
    [
        (-5),
        (-1),
        ('3'),
    ],
)
def test_lock_request_invalid_inputs(peer_ctx: Context[PeerRollingOpsCharm], max_retry: Any):
    peer = PeerRelation(endpoint='restart')
    state_in = State(leader=False, relations={peer})

    with peer_ctx(peer_ctx.on.update_status(), state_in) as mgr:
        with pytest.raises(RollingOpsInvalidLockRequestError):
            mgr.charm.restart_manager.request_async_lock(
                callback_id='_restart',
                kwargs={},
                max_retry=max_retry,
            )


@pytest.mark.parametrize(
    'callback_id',
    [
        ('',),
        ('   ',),
        ('unknown',),
    ],
)
def test_lock_request_invalid_callback_id(
    peer_ctx: Context[PeerRollingOpsCharm], callback_id: str
):
    peer = PeerRelation(endpoint='restart')
    state_in = State(leader=False, relations={peer})

    with peer_ctx(peer_ctx.on.update_status(), state_in) as mgr:
        with pytest.raises(RollingOpsInvalidLockRequestError, match='Unknown callback_id'):
            mgr.charm.restart_manager.request_async_lock(
                callback_id=callback_id,
                kwargs={},
                max_retry=0,
            )


@pytest.mark.parametrize(
    'kwargs',
    [
        ('nope'),
        ([]),
        ({'x': OperationQueue()}),
    ],
)
def test_lock_request_invalid_kwargs(peer_ctx: Context[PeerRollingOpsCharm], kwargs: Any):
    peer = PeerRelation(endpoint='restart')
    state_in = State(leader=False, relations={peer})

    with peer_ctx(peer_ctx.on.update_status(), state_in) as mgr:
        with pytest.raises(
            RollingOpsInvalidLockRequestError, match='Failed to create the lock request'
        ):
            mgr.charm.restart_manager.request_async_lock(
                callback_id='_restart',
                kwargs=kwargs,
                max_retry=0,
            )


def test_existing_operation_then_new_request(peer_ctx: Context[PeerRollingOpsCharm]):
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)
    peer = PeerRelation(
        endpoint='restart',
        local_unit_data={'state': LockIntent.REQUEST, 'operations': queue.to_string()},
    )

    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(peer_ctx.on.action('restart', params={'delay': 10}), state_in)

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.REQUEST
    result = OperationQueue.from_string(databag['operations'])

    assert len(result) == 2
    assert result.operations[0].callback_id == '_failed_restart'
    assert result.operations[1].callback_id == '_restart'


def test_new_request_does_not_overwrite_state_if_queue_not_empty(
    peer_ctx: Context[PeerRollingOpsCharm],
):
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)
    executed_at = now_timestamp_str()
    peer = PeerRelation(
        endpoint='restart',
        local_unit_data={
            'state': LockIntent.RETRY_RELEASE,
            'executed_at': executed_at,
            'operations': queue.to_string(),
        },
    )
    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(peer_ctx.on.action('restart', params={'delay': 10}), state_in)

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.RETRY_RELEASE
    assert databag['executed_at'] == executed_at
    result = OperationQueue.from_string(databag['operations'])
    assert len(result) == 2
    assert result.operations[0].callback_id == '_failed_restart'
    assert result.operations[1].callback_id == '_restart'


def test_relation_changed_without_grant_does_not_run_operation(
    peer_ctx: Context[PeerRollingOpsCharm],
):
    remote_unit_name = f'{peer_ctx.app_name}/1'
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)
    peer = PeerRelation(
        endpoint='restart',
        local_unit_data={'state': LockIntent.REQUEST, 'operations': queue.to_string()},
        local_app_data={'granted_unit': remote_unit_name, 'granted_at': now_timestamp_str()},
    )

    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(
        peer_ctx.on.relation_changed(peer, remote_unit=remote_unit_name), state_in
    )

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.REQUEST
    result = OperationQueue.from_string(databag['operations'])
    assert len(result) == 1
    assert databag.get('executed_at', '') == ''


def test_lock_complete_pops_head(peer_ctx: Context[PeerRollingOpsCharm]):
    remote_unit_name = f'{peer_ctx.app_name}/1'
    local_unit_name = f'{peer_ctx.app_name}/0'
    queue = _make_operation_queue(callback_id='_restart', kwargs={}, max_retry=0)
    peer = PeerRelation(
        endpoint='restart',
        local_unit_data={'state': LockIntent.REQUEST, 'operations': queue.to_string()},
        local_app_data={'granted_unit': local_unit_name, 'granted_at': now_timestamp_str()},
    )
    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(
        peer_ctx.on.relation_changed(peer, remote_unit=remote_unit_name), state_in
    )

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.IDLE
    assert databag['executed_at'] is not None
    assert databag.get('operations', None) == '[]'

    q = OperationQueue.from_string(databag['operations'])
    assert len(q) == 0


def test_successful_operation_leaves_state_request_when_more_ops_remain(
    peer_ctx: Context[PeerRollingOpsCharm],
):
    local_unit_name = f'{peer_ctx.app_name}/0'
    remote_unit_name = f'{peer_ctx.app_name}/1'
    queue = OperationQueue()
    op1 = Operation.create(callback_id='_restart', kwargs={}, max_retry=None)
    op2 = Operation.create(callback_id='_failed_restart', kwargs={}, max_retry=None)

    queue.enqueue(op1)
    queue.enqueue(op2)

    peer = PeerRelation(
        endpoint='restart',
        local_unit_data={'state': LockIntent.REQUEST, 'operations': queue.to_string()},
        local_app_data={'granted_unit': local_unit_name, 'granted_at': now_timestamp_str()},
    )

    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(
        peer_ctx.on.relation_changed(peer, remote_unit=remote_unit_name), state_in
    )

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.REQUEST
    q = OperationQueue.from_string(databag['operations'])
    assert len(q) == 1
    current_operation = q.peek()
    assert current_operation is not None
    assert current_operation.callback_id == '_failed_restart'


@pytest.mark.parametrize(
    'callback_id, lock_intent',
    [
        ('_failed_restart', LockIntent.RETRY_RELEASE),
        ('_deferred_restart', LockIntent.RETRY_HOLD),
    ],
)
def test_lock_retry_marks_retry(
    peer_ctx: Context[PeerRollingOpsCharm],
    callback_id: str,
    lock_intent: LockIntent,
):
    remote_unit_name = f'{peer_ctx.app_name}/1'
    local_unit_name = f'{peer_ctx.app_name}/0'
    queue = _make_operation_queue(callback_id=callback_id, kwargs={}, max_retry=3)
    peer = PeerRelation(
        endpoint='restart',
        local_unit_data={'state': LockIntent.REQUEST, 'operations': queue.to_string()},
        local_app_data={'granted_unit': local_unit_name, 'granted_at': now_timestamp_str()},
    )
    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(
        peer_ctx.on.relation_changed(peer, remote_unit=remote_unit_name), state_in
    )

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == lock_intent
    assert databag['executed_at'] is not None

    q = OperationQueue.from_string(databag['operations'])
    assert len(q) == 1
    current_operation = q.peek()
    initial_operation = queue.peek()
    assert current_operation is not None
    assert initial_operation is not None
    assert current_operation.callback_id == initial_operation.callback_id
    assert current_operation.kwargs == initial_operation.kwargs
    assert current_operation.max_retry == initial_operation.max_retry
    assert current_operation.requested_at == initial_operation.requested_at
    assert current_operation.attempt == 1


@pytest.mark.parametrize(
    'callback_id',
    [
        ('_failed_restart'),
        ('_deferred_restart'),
    ],
)
def test_lock_retry_drops_when_max_retry_reached(
    peer_ctx: Context[PeerRollingOpsCharm],
    callback_id: str,
):
    remote_unit_name = f'{peer_ctx.app_name}/1'
    local_unit_name = f'{peer_ctx.app_name}/0'

    queue = OperationQueue()
    op1 = Operation.create(callback_id=callback_id, kwargs={}, max_retry=3)
    queue.enqueue(op1)
    op = queue.peek()
    assert op is not None
    op.increase_attempt()
    op.increase_attempt()
    op.increase_attempt()

    peer = PeerRelation(
        endpoint='restart',
        local_unit_data={'state': LockIntent.REQUEST, 'operations': queue.to_string()},
        local_app_data={'granted_unit': local_unit_name, 'granted_at': now_timestamp_str()},
    )
    state_in = State(leader=False, relations={peer})

    state_out = peer_ctx.run(
        peer_ctx.on.relation_changed(peer, remote_unit=remote_unit_name), state_in
    )

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.IDLE
    assert databag['executed_at'] is not None

    q = OperationQueue.from_string(databag['operations'])
    assert len(q) == 0


def test_lock_grant_and_release(peer_ctx: Context[PeerRollingOpsCharm]):
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)
    peer = PeerRelation(
        endpoint='restart',
        peers_data={1: {'state': LockIntent.REQUEST, 'operations': queue.to_string()}},
    )
    state_in = State(leader=True, relations={peer})

    state = peer_ctx.run(peer_ctx.on.leader_elected(), state_in)
    databag = _app_databag(state, peer)

    unit_name = f'{peer_ctx.app_name}/1'
    assert unit_name in databag['granted_unit']
    assert databag['granted_at'] is not None


def test_scheduling_does_nothing_if_lock_already_granted(peer_ctx: Context[PeerRollingOpsCharm]):
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)
    remote_unit_name = f'{peer_ctx.app_name}/1'
    now_timestamp = now_timestamp_str()
    peer = PeerRelation(
        endpoint='restart',
        peers_data={
            1: {'state': LockIntent.REQUEST, 'operations': queue.to_string()},
            2: {'state': LockIntent.REQUEST, 'operations': queue.to_string()},
        },
        local_app_data={'granted_unit': remote_unit_name, 'granted_at': now_timestamp},
    )
    state_in = State(leader=True, relations={peer})

    state_out = peer_ctx.run(
        peer_ctx.on.relation_changed(peer, remote_unit=remote_unit_name), state_in
    )

    databag = _app_databag(state_out, peer)
    assert databag['granted_unit'] == remote_unit_name
    assert databag['granted_at'] == now_timestamp


def test_schedule_picks_retry_hold(peer_ctx: Context[PeerRollingOpsCharm]):
    old_operation = now_timestamp_str()
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)
    new_operation = now_timestamp_str()

    peer = PeerRelation(
        endpoint='restart',
        peers_data={
            1: {
                'state': LockIntent.RETRY_RELEASE,
                'operations': queue.to_string(),
                'executed_at': new_operation,
            },
            2: {
                'state': LockIntent.REQUEST,
                'operations': queue.to_string(),
                'executed_at': old_operation,
            },
            3: {
                'state': LockIntent.RETRY_HOLD,
                'operations': queue.to_string(),
                'executed_at': new_operation,
            },
        },
    )
    state_in = State(leader=True, relations={peer})

    state_out = peer_ctx.run(peer_ctx.on.leader_elected(), state_in)

    databag = _app_databag(state_out, peer)
    remote_unit_name = f'{peer_ctx.app_name}/3'
    assert databag['granted_unit'] == remote_unit_name


def test_schedule_picks_oldest_requested_at_among_requests(peer_ctx: Context[PeerRollingOpsCharm]):
    old_queue = OperationQueue()
    old_op = Operation.create(callback_id='restart', kwargs={}, max_retry=2)
    old_queue.enqueue(old_op)

    new_queue = OperationQueue()
    new_op = Operation.create(callback_id='restart', kwargs={}, max_retry=2)
    new_queue.enqueue(new_op)

    peer = PeerRelation(
        endpoint='restart',
        peers_data={
            1: {'state': LockIntent.REQUEST, 'operations': new_queue.to_string()},
            2: {'state': LockIntent.REQUEST, 'operations': old_queue.to_string()},
        },
    )
    state_in = State(leader=True, relations={peer})

    state_out = peer_ctx.run(peer_ctx.on.leader_elected(), state_in)
    databag = _app_databag(state_out, peer)
    remote_unit_name = f'{peer_ctx.app_name}/2'
    assert databag['granted_unit'] == remote_unit_name


def test_schedule_picks_oldest_executed_at_among_retries_when_no_requests(
    peer_ctx: Context[PeerRollingOpsCharm],
):
    old_operation = now_timestamp_str()
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)
    new_operation = now_timestamp_str()

    peer = PeerRelation(
        endpoint='restart',
        peers_data={
            1: {
                'state': LockIntent.RETRY_RELEASE,
                'operations': queue.to_string(),
                'executed_at': new_operation,
            },
            2: {
                'state': LockIntent.RETRY_RELEASE,
                'operations': queue.to_string(),
                'executed_at': old_operation,
            },
        },
    )
    state_in = State(leader=True, relations={peer})

    state_out = peer_ctx.run(peer_ctx.on.leader_elected(), state_in)

    databag = _app_databag(state_out, peer)
    remote_unit_name = f'{peer_ctx.app_name}/2'
    assert databag['granted_unit'] == remote_unit_name


def test_schedule_prioritizes_requests_over_retries(peer_ctx: Context[PeerRollingOpsCharm]):
    queue = _make_operation_queue(callback_id='_failed_restart', kwargs={}, max_retry=3)

    peer = PeerRelation(
        endpoint='restart',
        peers_data={
            1: {
                'state': LockIntent.RETRY_RELEASE,
                'operations': queue.to_string(),
                'executed_at': now_timestamp_str(),
            },
            2: {'state': LockIntent.REQUEST, 'operations': queue.to_string()},
        },
    )
    state_in = State(leader=True, relations={peer})

    state_out = peer_ctx.run(peer_ctx.on.leader_elected(), state_in)

    databag = _app_databag(state_out, peer)
    remote_unit_name = f'{peer_ctx.app_name}/2'
    assert databag['granted_unit'] == remote_unit_name


def test_no_unit_is_granted_if_there_are_no_requests(peer_ctx: Context[PeerRollingOpsCharm]):
    peer = PeerRelation(
        endpoint='restart',
        peers_data={1: {'state': LockIntent.IDLE}, 2: {'state': LockIntent.IDLE}},
    )
    state_in = State(leader=True, relations={peer})

    state_out = peer_ctx.run(peer_ctx.on.leader_elected(), state_in)

    databag = _app_databag(state_out, peer)
    assert databag.get('granted_unit', '') == ''
    assert databag.get('granted_at', '') == ''
