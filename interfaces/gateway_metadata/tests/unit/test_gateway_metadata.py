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

"""Unit tests for the gateway-metadata interface library."""

import ops
from ops.charm import CharmBase
from scenario import Context, Relation, State

from charmlibs.interfaces.gateway_metadata import (
    GatewayMetadata,
    GatewayMetadataProvider,
    GatewayMetadataRequirer,
)

PROVIDER_META = {
    'name': 'provider-charm',
    'provides': {'gateway-metadata': {'interface': 'gateway_metadata'}},
}

REQUIRER_META = {
    'name': 'requirer-charm',
    'requires': {'gateway-metadata': {'interface': 'gateway_metadata'}},
}

SAMPLE_METADATA = GatewayMetadata(
    namespace='istio-system',
    gateway_name='my-gateway',
    deployment_name='my-gateway-deploy',
    service_account='my-gateway-sa',
)


class ProviderCharm(CharmBase):
    META = PROVIDER_META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.gateway_metadata = GatewayMetadataProvider(self)
        self.framework.observe(
            self.on['gateway-metadata'].relation_joined, self._on_relation_joined
        )

    def _on_relation_joined(self, _: ops.EventBase) -> None:
        self.gateway_metadata.publish_metadata(SAMPLE_METADATA)


class RequirerCharm(CharmBase):
    META = REQUIRER_META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.gateway_metadata = GatewayMetadataRequirer(self)


def test_provider_publishes_metadata():
    relation = Relation(endpoint='gateway-metadata', interface='gateway_metadata')
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    state_out = ctx.run(
        ctx.on.relation_joined(relation=relation),
        State(relations=[relation], leader=True),
    )
    rel_out = state_out.get_relation(relation.id)
    parsed = GatewayMetadata.model_validate_json(rel_out.local_app_data['metadata'])
    assert parsed == SAMPLE_METADATA


def test_provider_skips_publish_when_not_leader():
    relation = Relation(endpoint='gateway-metadata', interface='gateway_metadata')
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    state_out = ctx.run(
        ctx.on.relation_joined(relation=relation),
        State(relations=[relation], leader=False),
    )
    rel_out = state_out.get_relation(relation.id)
    assert 'metadata' not in rel_out.local_app_data


def test_requirer_reads_metadata():
    relation = Relation(
        endpoint='gateway-metadata',
        interface='gateway_metadata',
        remote_app_name='gateway-app',
        remote_app_data={'metadata': SAMPLE_METADATA.model_dump_json()},
    )
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        charm = mgr.charm
        assert charm.gateway_metadata.is_ready is True
        assert charm.gateway_metadata.get_metadata() == SAMPLE_METADATA


def test_requirer_not_ready_when_no_data():
    relation = Relation(
        endpoint='gateway-metadata',
        interface='gateway_metadata',
        remote_app_name='gateway-app',
        remote_app_data={},
    )
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        assert mgr.charm.gateway_metadata.is_ready is False
        assert mgr.charm.gateway_metadata.get_metadata() is None
