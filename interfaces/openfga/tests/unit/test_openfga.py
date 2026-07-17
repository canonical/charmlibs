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

"""Unit tests for the openfga relation library."""

import ops
import ops.testing

from charmlibs.interfaces.openfga import (
    OpenfgaProviderAppData,
    OpenfgaProviderBaseData,
)
from conftest import ProviderCharm, RequirerCharm


def test_requirer_relation_created_leader(
    requirer_ctx: ops.testing.Context[RequirerCharm],
) -> None:
    """Test relation-created as a leader."""
    relation = ops.testing.Relation('openfga', remote_app_name='provider')
    state_in = ops.testing.State(leader=True, relations={relation})

    with requirer_ctx(requirer_ctx.on.relation_created(relation), state_in) as manager:
        state_out = manager.run()
        # Verify store name is set in our local app databag
        rel_out = state_out.get_relation(relation.id)
        assert rel_out.local_app_data.get('store_name') == 'my-store-name'


def test_requirer_relation_created_non_leader(
    requirer_ctx: ops.testing.Context[RequirerCharm],
) -> None:
    """Test relation-created as a non-leader."""
    relation = ops.testing.Relation('openfga', remote_app_name='provider')
    state_in = ops.testing.State(leader=False, relations={relation})

    with requirer_ctx(requirer_ctx.on.relation_created(relation), state_in) as manager:
        state_out = manager.run()
        # Verify app databag is empty for non-leader
        rel_out = state_out.get_relation(relation.id)
        assert not rel_out.local_app_data


def test_requirer_relation_changed_valid(requirer_ctx: ops.testing.Context[RequirerCharm]) -> None:
    """Test relation-changed with valid data from provider."""
    relation = ops.testing.Relation(
        'openfga',
        remote_app_name='provider',
        remote_app_data={
            'grpc_api_url': 'grpc://openfga:8081',
            'http_api_url': 'http://openfga:8080',
            'store_id': 'store-123',
        },
    )
    state_in = ops.testing.State(relations={relation})

    with requirer_ctx(requirer_ctx.on.relation_changed(relation), state_in) as manager:
        manager.run()
        assert manager.charm.events_emitted == [('created', 'store-123')]


def test_requirer_relation_changed_invalid(
    requirer_ctx: ops.testing.Context[RequirerCharm],
) -> None:
    """Test relation-changed with invalid data from provider."""
    relation = ops.testing.Relation(
        'openfga',
        remote_app_name='provider',
        remote_app_data={
            'grpc_api_url': 'grpc://openfga:8081',
            # missing http_api_url
        },
    )
    state_in = ops.testing.State(relations={relation})

    with requirer_ctx(requirer_ctx.on.relation_changed(relation), state_in) as manager:
        manager.run()
        assert not manager.charm.events_emitted


def test_requirer_relation_departed(requirer_ctx: ops.testing.Context[RequirerCharm]) -> None:
    """Test relation-departed."""
    relation = ops.testing.Relation('openfga', remote_app_name='provider')
    state_in = ops.testing.State(relations={relation})

    with requirer_ctx(requirer_ctx.on.relation_departed(relation), state_in) as manager:
        manager.run()
        assert len(manager.charm.events_emitted) == 1
        assert manager.charm.events_emitted[0][0] == 'removed'


def test_requirer_get_store_info_with_secret(
    requirer_ctx: ops.testing.Context[RequirerCharm],
) -> None:
    """Test get_store_info correctly loads secret."""
    relation = ops.testing.Relation(
        'openfga',
        remote_app_name='provider',
        remote_app_data={
            'grpc_api_url': 'grpc://openfga:8081',
            'http_api_url': 'http://openfga:8080',
            'store_id': 'store-123',
            'token_secret_id': 'secret-abc',
        },
    )
    secret = ops.testing.Secret(
        id='secret-abc',
        tracked_content={
            'token': 'my-secret-token',
        },
    )
    state_in = ops.testing.State(relations={relation}, secrets={secret})

    with requirer_ctx(requirer_ctx.on.start(), state_in) as manager:
        manager.run()
        info = manager.charm.openfga.get_store_info()
        assert info is not None
        assert info.grpc_api_url == 'grpc://openfga:8081'
        assert info.http_api_url == 'http://openfga:8080'
        assert info.store_id == 'store-123'
        assert info.token == 'my-secret-token'


def test_provider_relation_changed(provider_ctx: ops.testing.Context[ProviderCharm]) -> None:
    """Test provider relation changed."""
    relation = ops.testing.Relation(
        'openfga',
        remote_app_name='requirer',
        remote_app_data={
            'store_name': 'app-store',
        },
    )
    state_in = ops.testing.State(relations={relation})

    with provider_ctx(provider_ctx.on.relation_changed(relation), state_in) as manager:
        manager.run()
        assert manager.charm.events_emitted == [('requested', 'app-store', relation.id)]


def test_provider_update_relation_app_data_leader(
    provider_ctx: ops.testing.Context[ProviderCharm],
) -> None:
    """Test update_relation_app_data as leader."""
    relation = ops.testing.Relation('openfga', remote_app_name='requirer')
    state_in = ops.testing.State(leader=True, relations={relation})

    with provider_ctx(provider_ctx.on.start(), state_in) as manager:
        manager.run()
        data = OpenfgaProviderAppData(
            grpc_api_url='grpc://openfga:8081',
            http_api_url='http://openfga:8080',
            store_id='store-123',
        )
        manager.charm.openfga.update_relation_app_data(data, relation.id)

        # Check databag is updated
        rel_out = manager.charm.model.get_relation('openfga', relation.id)
        assert rel_out is not None
        assert rel_out.data[manager.charm.app].get('store_id') == 'store-123'
        assert rel_out.data[manager.charm.app].get('grpc_api_url') == 'grpc://openfga:8081'


def test_provider_update_relations_app_data(
    provider_ctx: ops.testing.Context[ProviderCharm],
) -> None:
    """Test update_relations_app_data updates multiple relations."""
    relation_1 = ops.testing.Relation('openfga', remote_app_name='requirer-1')
    relation_2 = ops.testing.Relation('openfga', remote_app_name='requirer-2')
    state_in = ops.testing.State(leader=True, relations={relation_1, relation_2})

    with provider_ctx(provider_ctx.on.start(), state_in) as manager:
        manager.run()
        data = OpenfgaProviderBaseData(
            grpc_api_url='grpc://new-openfga:8081',
            http_api_url='http://new-openfga:8080',
        )
        manager.charm.openfga.update_relations_app_data(data)

        rel_1_out = manager.charm.model.get_relation('openfga', relation_1.id)
        rel_2_out = manager.charm.model.get_relation('openfga', relation_2.id)

        assert rel_1_out is not None
        assert rel_2_out is not None
        assert rel_1_out.data[manager.charm.app].get('grpc_api_url') == 'grpc://new-openfga:8081'
        assert rel_2_out.data[manager.charm.app].get('grpc_api_url') == 'grpc://new-openfga:8081'
