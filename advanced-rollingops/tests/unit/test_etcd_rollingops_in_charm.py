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


from unittest.mock import MagicMock

from ops.testing import Context, PeerRelation, Secret, State
from tests.unit.conftest import RollingOpsCharm

from charmlibs.advanced_rollingops import (
    SECRET_FIELD,
)


def test_leader_elected_creates_shared_secret_and_stores_id(
    certificates_manager_patches: dict[str, MagicMock],
    etcdctl_patch: MagicMock,
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(endpoint='restart')

    state_in = State(leader=True, relations={peer_relation})
    state_out = ctx.run(ctx.on.leader_elected(), state_in)

    peer_out = next(r for r in state_out.relations if r.endpoint == 'restart')
    assert SECRET_FIELD in peer_out.local_app_data
    assert peer_out.local_app_data[SECRET_FIELD].startswith('secret:')

    certificates_manager_patches['generate'].assert_called_once()


def test_leader_elected_does_not_regenerate_when_secret_already_exists(
    certificates_manager_patches: dict[str, MagicMock],
    etcdctl_patch: MagicMock,
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(
        endpoint='restart', local_app_data={SECRET_FIELD: 'secret:existing'}
    )
    secret = Secret(
        id='secret:existing',
        owner='app',
        tracked_content={
            'client-cert': 'CERT_PEM',
            'client-key': 'KEY_PEM',
            'client-ca': 'CA_PEM',
        },
    )

    state_in = State(leader=True, relations={peer_relation}, secrets=[secret])

    state_out = ctx.run(ctx.on.leader_elected(), state_in)

    peer_out = next(r for r in state_out.relations if r.endpoint == 'restart')
    assert peer_out.local_app_data[SECRET_FIELD] == 'secret:existing'
    certificates_manager_patches['generate'].assert_not_called()


def test_non_leader_does_not_create_shared_secret(
    certificates_manager_patches: dict[str, MagicMock],
    etcdctl_patch: MagicMock,
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(endpoint='restart')
    state_in = State(leader=False, relations={peer_relation})

    state_out = ctx.run(ctx.on.relation_changed(peer_relation, remote_unit=1), state_in)

    peer_out = next(r for r in state_out.relations if r.endpoint == 'restart')
    assert SECRET_FIELD not in peer_out.local_app_data
    certificates_manager_patches['generate'].assert_not_called()


def test_relation_changed_syncs_local_certificate_from_secret(
    certificates_manager_patches: dict[str, MagicMock],
    etcdctl_patch: MagicMock,
    ctx: Context[RollingOpsCharm],
):
    peer_relation = PeerRelation(
        endpoint='restart', local_app_data={SECRET_FIELD: 'secret:rollingops-cert'}
    )

    secret = Secret(
        id='secret:rollingops-cert',
        tracked_content={
            'client-cert': 'CERT_PEM',
            'client-key': 'KEY_PEM',
            'client-ca': 'CA_PEM',
        },
    )

    state_in = State(leader=False, relations={peer_relation}, secrets=[secret])

    ctx.run(ctx.on.relation_changed(peer_relation, remote_unit=1), state_in)
    certificates_manager_patches['persist'].assert_called_once_with(
        'CERT_PEM', 'KEY_PEM', 'CA_PEM'
    )
