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

from unittest.mock import MagicMock, patch

import pytest
from ops.testing import Context, PeerRelation, Secret, State
from scenario import RawDataBagContents
from scenario.errors import UncaughtCharmError
from tests.unit.conftest import (
    VALID_CA_CERT_PEM,
    VALID_CLIENT_CERT_PEM,
    VALID_CLIENT_KEY_PEM,
    RollingOpsCharm,
)

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    PrivateKey,
)
from charmlibs.rollingops.common._exceptions import (
    RollingOpsInvalidSecretContentError,
)
from charmlibs.rollingops.common._models import (
    Operation,
    OperationQueue,
    ProcessingBackend,
    RollingOpsStatus,
)
from charmlibs.rollingops.etcd._models import SharedCertificate
from charmlibs.rollingops.etcd._relations import CERT_SECRET_FIELD
from charmlibs.rollingops.peer._models import LockIntent


def _unit_databag(state: State, peer: PeerRelation) -> RawDataBagContents:
    return state.get_relation(peer.id).local_unit_data


def test_leader_elected_creates_shared_secret_and_stores_id(
    certificates_manager_patches: dict[str, MagicMock],
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(endpoint='restart')

    state_in = State(leader=True, relations={peer_relation})
    state_out = ctx.run(ctx.on.leader_elected(), state_in)

    peer_out = next(r for r in state_out.relations if r.endpoint == 'restart')
    assert CERT_SECRET_FIELD in peer_out.local_app_data
    assert peer_out.local_app_data[CERT_SECRET_FIELD].startswith('secret:')

    certificates_manager_patches['generate'].assert_called_once()


def test_leader_elected_does_not_regenerate_when_secret_already_exists(
    certificates_manager_patches: dict[str, MagicMock],
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(
        endpoint='restart', local_app_data={CERT_SECRET_FIELD: 'secret:existing'}
    )
    secret = Secret(
        id='secret:existing',
        owner='app',
        tracked_content={
            'client-cert': VALID_CLIENT_CERT_PEM,
            'client-key': VALID_CLIENT_KEY_PEM,
            'client-ca': VALID_CA_CERT_PEM,
        },
    )

    state_in = State(leader=True, relations={peer_relation}, secrets=[secret])

    state_out = ctx.run(ctx.on.leader_elected(), state_in)

    peer_out = next(r for r in state_out.relations if r.endpoint == 'restart')
    assert peer_out.local_app_data[CERT_SECRET_FIELD] == 'secret:existing'
    certificates_manager_patches['generate'].assert_not_called()


def test_non_leader_does_not_create_shared_secret(
    certificates_manager_patches: dict[str, MagicMock],
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(endpoint='restart')
    state_in = State(leader=False, relations={peer_relation})

    state_out = ctx.run(ctx.on.relation_changed(peer_relation, remote_unit=1), state_in)

    peer_out = next(r for r in state_out.relations if r.endpoint == 'restart')
    assert CERT_SECRET_FIELD not in peer_out.local_app_data
    certificates_manager_patches['generate'].assert_not_called()


def test_relation_changed_syncs_local_certificate_from_secret(
    certificates_manager_patches: dict[str, MagicMock],
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(
        endpoint='restart', local_app_data={CERT_SECRET_FIELD: 'secret:rollingops-cert'}
    )

    secret = Secret(
        id='secret:rollingops-cert',
        tracked_content={
            'client-cert': VALID_CLIENT_CERT_PEM,
            'client-key': VALID_CLIENT_KEY_PEM,
            'client-ca': VALID_CA_CERT_PEM,
        },
    )

    state_in = State(leader=False, relations={peer_relation}, secrets=[secret])
    expected_shared = SharedCertificate(
        certificate=Certificate.from_string(VALID_CLIENT_CERT_PEM),
        key=PrivateKey.from_string(VALID_CLIENT_KEY_PEM),
        ca=Certificate.from_string(VALID_CA_CERT_PEM),
    )
    ctx.run(ctx.on.relation_changed(peer_relation, remote_unit=1), state_in)
    certificates_manager_patches['persist'].assert_called_once_with(expected_shared)


def test_invalid_certificate_secret_content_raises(
    certificates_manager_patches: dict[str, MagicMock],
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(
        endpoint='restart', local_app_data={CERT_SECRET_FIELD: 'secret:rollingops-cert'}
    )

    secret = Secret(
        id='secret:rollingops-cert',
        tracked_content={
            'client-cert': '',
            'client-key': 'KEY_PEM',
            'client-ca': 'CA_PEM',
        },
    )

    state_in = State(leader=False, relations={peer_relation}, secrets=[secret])
    with pytest.raises(UncaughtCharmError) as exc_info:
        ctx.run(ctx.on.relation_changed(peer_relation, remote_unit=1), state_in)
        assert isinstance(exc_info.value.__cause__, RollingOpsInvalidSecretContentError)


def test_on_restart_action_lock_fallbacks_to_peer(
    ctx: Context[RollingOpsCharm],
):
    peer = PeerRelation(endpoint='restart')
    state_in = State(leader=False, relations={peer})

    state_out = ctx.run(
        ctx.on.action('restart', params={'delay': 10}),
        state_in,
    )

    databag = _unit_databag(state_out, peer)
    assert databag['state'] == LockIntent.REQUEST
    assert databag['operations']
    assert databag['processing_backend'] == ProcessingBackend.PEER
    assert databag['etcd_cleanup_needed'] == 'true'

    q = OperationQueue.from_string(databag['operations'])
    assert len(q) == 1
    operation = q.peek()
    assert operation is not None
    assert operation.callback_id == '_restart'
    assert operation.kwargs == {'delay': 10}
    assert operation.max_retry is None
    assert operation.requested_at is not None


def test_state_not_initialized(ctx: Context[RollingOpsCharm]):
    state = State(leader=True)

    with ctx(ctx.on.start(), state) as mgr:
        rolling_state = mgr.charm.restart_manager.state
        assert rolling_state.status == RollingOpsStatus.NOT_READY
        assert rolling_state.processing_backend == ProcessingBackend.PEER
        assert len(rolling_state.operations) == 0
        assert mgr.charm.restart_manager.is_ready() is False


def test_state_peer_idle(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        local_unit_data={
            'state': '',
            'operations': '',
            'executed_at': '',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        rolling_state = mgr.charm.restart_manager.state
        assert rolling_state.status == RollingOpsStatus.IDLE
        assert rolling_state.processing_backend == ProcessingBackend.PEER
        assert len(rolling_state.operations) == 0
        assert mgr.charm.restart_manager.is_ready() is True


def test_state_peer_waiting(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        local_unit_data={
            'state': 'request',
            'operations': OperationQueue([
                Operation.create('restart', {'delay': 1}, max_retry=2)
            ]).to_string(),
            'executed_at': '',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        rolling_state = mgr.charm.restart_manager.state
        assert rolling_state.status == RollingOpsStatus.WAITING
        assert rolling_state.processing_backend == ProcessingBackend.PEER
        assert len(rolling_state.operations) == 1
        assert mgr.charm.restart_manager.is_ready() is True


def test_state_peer_is_granted(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        local_app_data={
            'granted_unit': f'{ctx.app_name}/0',
        },
        local_unit_data={
            'state': 'retry-release',
            'operations': OperationQueue([
                Operation.create('restart', {'delay': 1}, max_retry=2)
            ]).to_string(),
            'executed_at': '2026-04-09T10:01:00+00:00',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        rolling_state = mgr.charm.restart_manager.state
        assert rolling_state.status == RollingOpsStatus.GRANTED
        assert rolling_state.processing_backend == ProcessingBackend.PEER
        assert len(rolling_state.operations) == 1
        assert mgr.charm.restart_manager.is_ready() is True


def test_state_peer_waiting_retry(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        local_app_data={
            'granted_unit': 'myapp/0',
        },
        local_unit_data={
            'state': 'retry-release',
            'operations': OperationQueue([
                Operation.create('restart', {'delay': 1}, max_retry=2)
            ]).to_string(),
            'executed_at': '2026-04-09T10:01:00+00:00',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        rolling_state = mgr.charm.restart_manager.state
        assert rolling_state.status == RollingOpsStatus.WAITING
        assert rolling_state.processing_backend == ProcessingBackend.PEER
        assert len(rolling_state.operations) == 1
        assert mgr.charm.restart_manager.is_ready() is True


def test_state_etcd_status(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        interface='rollingops',
        local_app_data={},
        local_unit_data={
            'state': '',
            'operations': OperationQueue([
                Operation.create('restart', {'delay': 1}, max_retry=2)
            ]).to_string(),
            'executed_at': '',
            'processing_backend': 'etcd',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with patch(
        'charmlibs.rollingops.etcd._backend.EtcdRollingOpsBackend.get_status',
        return_value=RollingOpsStatus.GRANTED,
    ):
        with ctx(ctx.on.update_status(), state) as mgr:
            rolling_state = mgr.charm.restart_manager.state
            assert rolling_state.status == RollingOpsStatus.GRANTED
            assert rolling_state.processing_backend == ProcessingBackend.ETCD
            assert len(rolling_state.operations) == 1
            assert mgr.charm.restart_manager.is_ready() is True


def test_state_falls_back_to_peer_if_etcd_status_fails(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        interface='rollingops',
        local_app_data={},
        local_unit_data={
            'state': 'request',
            'operations': OperationQueue([Operation.create('restart', {'delay': 1})]).to_string(),
            'executed_at': '',
            'processing_backend': 'etcd',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with patch(
        'charmlibs.rollingops._rollingops_manager.EtcdRollingOpsBackend.get_status',
        return_value=RollingOpsStatus.NOT_READY,
    ):
        with ctx(ctx.on.update_status(), state) as mgr:
            rolling_state = mgr.charm.restart_manager.state
            assert rolling_state.status == RollingOpsStatus.WAITING
            assert rolling_state.processing_backend == ProcessingBackend.PEER
            assert len(rolling_state.operations) == 1
            assert mgr.charm.restart_manager.is_ready() is True


def test_is_waiting_returns_true_when_matching_operation_exists(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        interface='rollingops',
        local_app_data={},
        local_unit_data={
            'state': 'request',
            'operations': OperationQueue([
                Operation.create('restart', {'delay': 1}),
                Operation.create('restart', {'delay': 2}),
            ]).to_string(),
            'executed_at': '',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        assert mgr.charm.restart_manager.is_waiting('restart', {'delay': 1}) is True
        assert mgr.charm.restart_manager.is_ready() is True


def test_is_waiting_returns_false_when_callback_matches_but_kwargs_do_not(
    ctx: Context[RollingOpsCharm],
):
    peer_rel = PeerRelation(
        endpoint='restart',
        interface='rollingops',
        local_app_data={},
        local_unit_data={
            'state': 'request',
            'operations': OperationQueue([
                Operation.create('restart', {'delay': 1}),
            ]).to_string(),
            'executed_at': '',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        assert mgr.charm.restart_manager.is_waiting('restart', {'delay': 2}) is False
        assert mgr.charm.restart_manager.is_ready() is True


def test_is_waiting_returns_false_when_callback_does_not_match(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        interface='rollingops',
        local_app_data={},
        local_unit_data={
            'state': 'request',
            'operations': OperationQueue([
                Operation.create('restart', {'delay': 1}),
            ]).to_string(),
            'executed_at': '',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        assert mgr.charm.restart_manager.is_waiting('other-callback', {'delay': 1}) is False
        assert mgr.charm.restart_manager.is_ready() is True


def test_is_waiting_returns_true_when_kwargs_is_none_and_matching_operation_has_empty_kwargs(
    ctx: Context[RollingOpsCharm],
):
    peer_rel = PeerRelation(
        endpoint='restart',
        interface='rollingops',
        local_app_data={},
        local_unit_data={
            'state': 'request',
            'operations': OperationQueue([
                Operation.create('restart', {}),
            ]).to_string(),
            'executed_at': '',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        assert mgr.charm.restart_manager.is_waiting('restart') is True
        assert mgr.charm.restart_manager.is_ready() is True


def test_is_waiting_returns_false_when_operation_validation_fails(ctx: Context[RollingOpsCharm]):
    peer_rel = PeerRelation(
        endpoint='restart',
        interface='rollingops',
        local_app_data={},
        local_unit_data={
            'state': 'request',
            'operations': OperationQueue([]).to_string(),
            'executed_at': '',
            'processing_backend': 'peer',
            'etcd_cleanup_needed': 'false',
        },
    )
    state = State(leader=False, relations={peer_rel})

    with ctx(ctx.on.update_status(), state) as mgr:
        assert mgr.charm.restart_manager.is_waiting('restart', 'a') is False  # type: ignore[reportArgumentType]
        assert mgr.charm.restart_manager.is_ready() is True
