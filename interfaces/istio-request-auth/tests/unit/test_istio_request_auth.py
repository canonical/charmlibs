# Copyright 2025 Canonical Ltd.
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

"""Unit tests for the istio-request-auth interface library."""

import json

import ops
from ops.charm import CharmBase
from scenario import Context, Relation, State

from charmlibs.interfaces.istio_request_auth import (
    ClaimToHeader,
    IstioRequestAuthProvider,
    IstioRequestAuthRequirer,
    JWTRule,
)
from charmlibs.interfaces.istio_request_auth._istio_request_auth import _RequestAuthData

PROVIDER_META = {
    'name': 'provider-charm',
    'provides': {'istio-request-auth': {'interface': 'istio_request_auth'}},
}

REQUIRER_META = {
    'name': 'requirer-charm',
    'requires': {'istio-request-auth': {'interface': 'istio_request_auth'}},
}


def _sample_jwt_rules():
    return [
        JWTRule(
            issuer='https://example.com',
            forward_original_token=True,
            claim_to_headers=[
                ClaimToHeader(header='x-user-id', claim='email'),
                ClaimToHeader(header='x-user-id', claim='sub'),
            ],
        ),
    ]


def _sample_multi_issuer():
    return [
        JWTRule(
            issuer='https://local-hydra.example.com',
            jwks_uri='https://local-hydra.example.com/.well-known/jwks.json',
            claim_to_headers=[
                ClaimToHeader(header='x-user-email', claim='email'),
            ],
        ),
        JWTRule(
            issuer='https://external-idp.example.com',
            claim_to_headers=[
                ClaimToHeader(header='x-user-email', claim='email'),
            ],
        ),
    ]


def _databag_for(rules: list[JWTRule]) -> dict[str, str]:
    """Build a databag dict matching what Relation.save(RequestAuthData) produces."""
    data = _RequestAuthData(jwt_rules=rules)
    return {'jwt_rules': json.dumps(data.model_dump(mode='json')['jwt_rules'])}


class ProviderCharm(CharmBase):
    META = PROVIDER_META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.request_auth = IstioRequestAuthProvider(self)


class RequirerCharm(CharmBase):
    META = REQUIRER_META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.request_auth = IstioRequestAuthRequirer(self)
        self.framework.observe(
            self.on['istio-request-auth'].relation_changed, self._on_relation_changed
        )

    def _on_relation_changed(self, _: ops.EventBase) -> None:
        self.request_auth.publish_data(_sample_jwt_rules())


def test_requirer_publishes_jwt_rules_as_top_level_key():
    relation = Relation(endpoint='istio-request-auth', interface='istio_request_auth')
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    state_out = ctx.run(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    )
    rel_out = state_out.get_relation(relation.id)
    assert 'jwt_rules' in rel_out.local_app_data
    parsed = json.loads(rel_out.local_app_data['jwt_rules'])
    assert len(parsed) == 1
    assert parsed[0]['issuer'] == 'https://example.com'
    assert parsed[0]['forward_original_token'] is True
    assert len(parsed[0]['claim_to_headers']) == 2


def test_requirer_skips_publish_when_not_leader():
    relation = Relation(endpoint='istio-request-auth', interface='istio_request_auth')
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    state_out = ctx.run(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=False),
    )
    rel_out = state_out.get_relation(relation.id)
    assert 'jwt_rules' not in rel_out.local_app_data


def test_provider_reads_from_single_relation():
    relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='my-app',
        remote_app_data=_databag_for(_sample_jwt_rules()),
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert 'my-app' in data
        assert data['my-app'][0].issuer == 'https://example.com'
        assert mgr.charm.request_auth.is_ready is True


def test_provider_reads_from_multiple_relations():
    relation_1 = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='app-one',
        remote_app_data=_databag_for(_sample_jwt_rules()),
    )
    relation_2 = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='app-two',
        remote_app_data=_databag_for(_sample_multi_issuer()),
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation_1),
        State(relations=[relation_1, relation_2], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert len(data) == 2
        assert len(data['app-one']) == 1
        assert len(data['app-two']) == 2


def test_provider_not_ready_when_no_relations():
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(ctx.on.start(), State(leader=True)) as mgr:
        assert mgr.charm.request_auth.is_ready is False
        assert mgr.charm.request_auth.get_data() == {}


def test_provider_skips_app_with_no_databag_keys():
    """App connected but empty databag — should be skipped."""
    relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='bad-app',
        remote_app_data={},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert 'bad-app' not in data
        assert mgr.charm.request_auth.is_ready is False


def test_provider_skips_app_with_null_jwt_rules():
    """App wrote jwt_rules as null — should be skipped."""
    relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='null-app',
        remote_app_data={'jwt_rules': 'null'},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert 'null-app' not in data


def test_provider_skips_app_with_empty_jwt_rules():
    """App connected with empty jwt_rules list — should be skipped."""
    relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='empty-app',
        remote_app_data={'jwt_rules': '[]'},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert 'empty-app' not in data


def test_provider_skips_app_with_invalid_json():
    """App connected with unparseable jwt_rules — should be skipped."""
    relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='broken-app',
        remote_app_data={'jwt_rules': 'not-json'},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert 'broken-app' not in data


def test_get_connected_apps_includes_all():
    """get_connected_apps returns all apps regardless of data validity."""
    good_relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='good-app',
        remote_app_data=_databag_for(_sample_jwt_rules()),
    )
    bad_relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='bad-app',
        remote_app_data={},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=good_relation),
        State(relations=[good_relation, bad_relation], leader=True),
    ) as mgr:
        connected = mgr.charm.request_auth.get_connected_apps()
        assert connected == {'good-app', 'bad-app'}
        valid = mgr.charm.request_auth.get_data()
        invalid = connected - set(valid.keys())
        assert invalid == {'bad-app'}
