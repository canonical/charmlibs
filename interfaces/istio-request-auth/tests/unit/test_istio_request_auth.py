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

import ops
from ops.charm import CharmBase
from scenario import Context, Relation, State

from charmlibs.interfaces.istio_request_auth import (
    ClaimToHeaderData,
    IstioRequestAuthProvider,
    IstioRequestAuthRequirer,
    JWTRuleData,
    RequestAuthData,
)

PROVIDER_META = {
    'name': 'provider-charm',
    'provides': {'istio-request-auth': {'interface': 'istio_request_auth'}},
}

REQUIRER_META = {
    'name': 'requirer-charm',
    'requires': {'istio-request-auth': {'interface': 'istio_request_auth'}},
}


def _sample_auth_data():
    return RequestAuthData(
        jwt_rules=[
            JWTRuleData(
                issuer='https://example.com',
                forward_original_token=True,
                claim_to_headers=[
                    ClaimToHeaderData(header='x-user-id', claim='email'),
                    ClaimToHeaderData(header='x-user-id', claim='client_id'),
                ],
            ),
        ]
    )


def _sample_multi_issuer():
    return RequestAuthData(
        jwt_rules=[
            JWTRuleData(
                issuer='https://local-hydra.example.com',
                jwks_uri='https://local-hydra.example.com/.well-known/jwks.json',
                claim_to_headers=[
                    ClaimToHeaderData(header='x-user-email', claim='email'),
                ],
            ),
            JWTRuleData(
                issuer='https://external-idp.example.com',
                claim_to_headers=[
                    ClaimToHeaderData(header='x-user-email', claim='email'),
                ],
            ),
        ]
    )


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
        self.request_auth.publish_data(_sample_auth_data())


def test_requirer_publishes_data():
    relation = Relation(endpoint='istio-request-auth', interface='istio_request_auth')
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    state_out = ctx.run(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    )
    rel_out = state_out.get_relation(relation.id)
    parsed = RequestAuthData.model_validate_json(rel_out.local_app_data['request_auth_data'])
    assert len(parsed.jwt_rules) == 1
    assert parsed.jwt_rules[0].issuer == 'https://example.com'
    assert parsed.jwt_rules[0].forward_original_token is True
    assert parsed.jwt_rules[0].claim_to_headers is not None
    assert len(parsed.jwt_rules[0].claim_to_headers) == 2


def test_requirer_skips_publish_when_not_leader():
    relation = Relation(endpoint='istio-request-auth', interface='istio_request_auth')
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    state_out = ctx.run(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=False),
    )
    rel_out = state_out.get_relation(relation.id)
    assert 'request_auth_data' not in rel_out.local_app_data


def test_provider_reads_from_single_relation():
    auth_data = _sample_auth_data()
    relation = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='my-app',
        remote_app_data={'request_auth_data': auth_data.model_dump_json()},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert 'my-app' in data
        assert data['my-app'].jwt_rules[0].issuer == 'https://example.com'
        assert mgr.charm.request_auth.is_ready is True


def test_provider_reads_from_multiple_relations():
    relation_1 = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='app-one',
        remote_app_data={'request_auth_data': _sample_auth_data().model_dump_json()},
    )
    relation_2 = Relation(
        endpoint='istio-request-auth',
        interface='istio_request_auth',
        remote_app_name='app-two',
        remote_app_data={'request_auth_data': _sample_multi_issuer().model_dump_json()},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation_1),
        State(relations=[relation_1, relation_2], leader=True),
    ) as mgr:
        data = mgr.charm.request_auth.get_data()
        assert len(data) == 2
        assert len(data['app-one'].jwt_rules) == 1
        assert len(data['app-two'].jwt_rules) == 2


def test_provider_not_ready_when_no_relations():
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(ctx.on.start(), State(leader=True)) as mgr:
        assert mgr.charm.request_auth.is_ready is False
        assert mgr.charm.request_auth.get_data() == {}
