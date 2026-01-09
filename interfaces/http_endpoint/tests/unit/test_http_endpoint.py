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

"""Tests for HttpEndpointProvider and HttpEndpointRequirer."""

from typing import Any

import ops
import ops.testing

from conftest import ProviderCharm, RequirerCharm


class TestHttpEndpointProvider:
    """Tests for HttpEndpointProvider."""

    def test_publishes_endpoint_data_on_relation_changed(
        self, provider_charm_meta: dict[str, Any], provider_charm_relation: ops.testing.Relation
    ):
        """Test that the provider publishes endpoint data when the relation changes."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation = provider_charm_relation

        state_in = ops.testing.State(
            leader=True,
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            # Update config before emitting the event
            manager.charm.provider.update_config(scheme='http', listen_port=8080)
            manager.run()

            # Check the relation data on the charm
            rel = manager.charm.model.relations['http-endpoint'][0]
            assert rel.data[manager.charm.app]['port'] == '8080'
            assert rel.data[manager.charm.app]['scheme'] == 'http'

    def test_update_config_emits_config_changed_event(
        self, provider_charm_meta: dict[str, Any], provider_charm_relation: ops.testing.Relation
    ):
        """Test that update_config emits the config_changed event."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation = provider_charm_relation

        state_in = ops.testing.State(
            leader=True,
            relations=[relation],
        )

        with ctx(ctx.on.start(), state_in) as manager:
            # Before update_config, relation data should be empty
            rel = manager.charm.model.relations['http-endpoint'][0]
            assert 'port' not in rel.data[manager.charm.app]
            assert 'scheme' not in rel.data[manager.charm.app]

            manager.charm.provider.update_config(scheme='https', listen_port=443)

            # The update_config should emit http_endpoint_config_changed which triggers _configure
            rel = manager.charm.model.relations['http-endpoint'][0]
            assert rel.data[manager.charm.app]['port'] == '443'
            assert rel.data[manager.charm.app]['scheme'] == 'https'

    def test_non_leader_does_not_publish(
        self, provider_charm_meta: dict[str, Any], provider_charm_relation: ops.testing.Relation
    ):
        """Test that non-leader units do not publish endpoint data."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation = provider_charm_relation

        state_in = ops.testing.State(
            leader=False,
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            manager.charm.provider.update_config(scheme='http', listen_port=8080)
            manager.run()

            # Non-leader should not update relation data
            rel = manager.charm.model.relations['http-endpoint'][0]
            assert dict(rel.data[manager.charm.app]) == {}

    def test_emits_config_required_when_config_incomplete(
        self, provider_charm_meta: dict[str, Any], provider_charm_relation: ops.testing.Relation
    ):
        """Test that provider emits config_required event when configuration is incomplete."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation = provider_charm_relation

        state_in = ops.testing.State(
            leader=True,
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            # Set the charm to have no config
            manager.charm.provider_config = {}
            manager.run()

            # The provider should not have published data since config is incomplete
            rel = manager.charm.model.relations['http-endpoint'][0]
            assert dict(rel.data[manager.charm.app]) == {}

    def test_no_relations(self, provider_charm_meta: dict[str, Any]):
        """Test that provider handles gracefully when there are no relations."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        state_in = ops.testing.State(
            leader=True,
            relations=[],
        )

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.provider.update_config(scheme='http', listen_port=8080)
            manager.run()

            # Should not have any relations anymore
            rel = manager.charm.model.relations['http-endpoint']
            assert len(rel) == 0

    def test_multiple_relations(
        self, provider_charm_meta: dict[str, Any], provider_charm_relation: ops.testing.Relation
    ):
        """Test that provider publishes to multiple relations."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation1 = provider_charm_relation

        relation2 = ops.testing.Relation(
            endpoint='http-endpoint',
            interface='http_endpoint',
        )

        state_in = ops.testing.State(
            leader=True,
            relations=[relation1, relation2],
        )

        with ctx(ctx.on.relation_changed(relation1), state_in) as manager:
            manager.charm.provider.update_config(scheme='https', listen_port=8443)
            manager.run()

            # Both relations should have the data
            relations = manager.charm.model.relations['http-endpoint']
            assert len(relations) == 2

            for rel in relations:
                assert rel.data[manager.charm.app]['port'] == '8443'
                assert rel.data[manager.charm.app]['scheme'] == 'https'

    def test_relation_broken(
        self, provider_charm_meta: dict[str, Any], provider_charm_relation: ops.testing.Relation
    ):
        """Test that provider handles relation broken events."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation = provider_charm_relation

        state_in = ops.testing.State(
            leader=True,
            relations=[relation],
        )

        with ctx(ctx.on.relation_broken(relation), state_in) as manager:
            manager.charm.provider.update_config(scheme='http', listen_port=8080)
            manager.run()

            rel = manager.charm.model.relations['http-endpoint']
            assert len(rel) == 0


class TestHttpEndpointRequirer:
    """Tests for HttpEndpointRequirer."""

    def test_receives_endpoint_data(
        self, requirer_charm_meta: dict[str, Any], requirer_charm_relation_1: ops.testing.Relation
    ):
        """Test that the requirer receives and parses endpoint data correctly."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation = requirer_charm_relation_1

        state_in = ops.testing.State(
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 1
            assert endpoints[0].port == '8080'
            assert endpoints[0].scheme == 'http'
            assert endpoints[0].hostname == '10.0.0.1'

    def test_charm_upgrade_receives_endpoint_data(
        self, requirer_charm_meta: dict[str, Any], requirer_charm_relation_1: ops.testing.Relation
    ):
        """Test that the requirer receives and parses endpoint data correctly after upgrade."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation = requirer_charm_relation_1

        state_in = ops.testing.State(
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 1
            assert endpoints[0].port == '8080'
            assert endpoints[0].scheme == 'http'
            assert endpoints[0].hostname == '10.0.0.1'

        with ctx(ctx.on.upgrade_charm(), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 1
            assert endpoints[0].port == '8080'
            assert endpoints[0].scheme == 'http'
            assert endpoints[0].hostname == '10.0.0.1'

    def test_charm_config_changed_receives_endpoint_data(
        self, requirer_charm_meta: dict[str, Any], requirer_charm_relation_1: ops.testing.Relation
    ):
        """Test that the requirer receives and parses endpoint data correctly after configuring."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation = requirer_charm_relation_1

        state_in = ops.testing.State(
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 1
            assert endpoints[0].port == '8080'
            assert endpoints[0].scheme == 'http'
            assert endpoints[0].hostname == '10.0.0.1'

        with ctx(ctx.on.config_changed(), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 1
            assert endpoints[0].port == '8080'
            assert endpoints[0].scheme == 'http'
            assert endpoints[0].hostname == '10.0.0.1'

    def test_emits_unavailable_when_no_relations(self, requirer_charm_meta: dict[str, Any]):
        """Test that requirer emits unavailable event when there are no relations."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        state_in = ops.testing.State(
            relations=[],
        )

        with ctx(ctx.on.start(), state_in) as manager:
            # Manually trigger _configure to simulate relation-changed
            manager.charm.requirer._configure(
                ops.EventBase(ops.Handle(manager.charm, 'test', 'test'))
            )

            # Should have no endpoints available
            assert len(manager.charm.endpoints) == 0

    def test_handles_relation_broken(
        self, requirer_charm_meta: dict[str, Any], requirer_charm_relation_1: ops.testing.Relation
    ):
        """Test that requirer handles relation broken events."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation = requirer_charm_relation_1

        state_in = ops.testing.State(
            relations=[relation],
        )

        with ctx(ctx.on.relation_broken(relation), state_in) as manager:
            manager.run()
            # Should have no endpoints after relation is broken
            assert len(manager.charm.endpoints) == 0

    def test_multiple_relations(
        self,
        requirer_charm_meta: dict[str, Any],
        requirer_charm_relation_1: ops.testing.Relation,
        requirer_charm_relation_2: ops.testing.Relation,
    ):
        """Test that requirer can handle multiple relations."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation1 = requirer_charm_relation_1
        relation2 = requirer_charm_relation_2

        state_in = ops.testing.State(
            relations=[relation1, relation2],
        )

        with ctx(ctx.on.relation_changed(relation1), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 2

            # Check endpoints (order may vary)
            schemes = {ep.scheme for ep in endpoints}
            ports = {ep.port for ep in endpoints}
            hostnames = {ep.hostname for ep in endpoints}

            assert schemes == {'http', 'https'}
            assert ports == {'8080', '8443'}
            assert hostnames == {'10.0.0.1', '10.0.0.2'}

    def test_empty_relation_data(self, requirer_charm_meta: dict[str, Any]):
        """Test that requirer handles relations with no data gracefully."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation = ops.testing.Relation(
            endpoint='http-endpoint',
            interface='http_endpoint',
            remote_app_data={},
        )

        state_in = ops.testing.State(
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            manager.run()

            # Should have no valid endpoints
            assert len(manager.charm.endpoints) == 0
