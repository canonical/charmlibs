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
import pytest
from pydantic import HttpUrl

from charmlibs.interfaces.http_endpoint._http_endpoint import (
    DataValidationError,
    HttpEndpointDataModel,
)
from conftest import ProviderCharm, RequirerCharm


class TestHttpEndpointDataModel:
    """Tests for HttpEndpointDataModel."""

    def test_valid_url(self):
        """Test that a valid URL is accepted and can be dumped/loaded."""
        # Create a model with a valid URL
        model = HttpEndpointDataModel(url=HttpUrl('https://example.com:8443/api'))

        # Dump to databag format
        databag = model.dump()

        # Verify the databag format
        assert 'url' in databag
        assert isinstance(databag['url'], str)

        # Load back from databag
        loaded_model = HttpEndpointDataModel.load(databag)

        # Verify the loaded model matches
        assert str(loaded_model.url) == str(model.url)

    def test_invalid_url(self):
        """Test that an invalid URL raises DataValidationError."""
        # Create an invalid databag with malformed URL
        invalid_databag = {'url': '"not-a-valid-url"'}

        # Should raise DataValidationError when loading
        with pytest.raises(DataValidationError, match='failed to validate databag'):
            HttpEndpointDataModel.load(invalid_databag)

    def test_invalid_json(self):
        """Test that invalid JSON in databag raises DataValidationError."""
        # Create a databag with invalid JSON
        invalid_databag = {'url': 'not-valid-json{'}

        # Should raise DataValidationError when loading
        with pytest.raises(DataValidationError, match='invalid databag contents'):
            HttpEndpointDataModel.load(invalid_databag)


class TestHttpEndpointProvider:
    """Tests for HttpEndpointProvider."""

    def test_publishes_endpoint_data_on_relation_changed(
        self,
        provider_charm_meta: dict[str, Any],
        provider_charm_relation_1: ops.testing.Relation,
        provider_charm_relation_2: ops.testing.Relation,
    ):
        """Test that the provider publishes endpoint data when the relation changes."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation1 = provider_charm_relation_1
        relation2 = provider_charm_relation_2

        state_in = ops.testing.State(
            leader=True,
            relations=[relation1, relation2],
        )

        with ctx(ctx.on.relation_changed(relation1), state_in) as manager:
            manager.run()

            # Both relations should have the data
            relations = manager.charm.model.relations['http-endpoint']
            assert len(relations) == 2

            for rel in relations:
                assert rel.data[manager.charm.app] != {}

    def test_update_config_emits_config_changed_event(
        self,
        provider_charm_meta: dict[str, Any],
        provider_charm_relation_1: ops.testing.Relation,
        provider_charm_relation_2: ops.testing.Relation,
    ):
        """Test that update_config emits the config_changed event."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation_1 = provider_charm_relation_1
        relation_2 = provider_charm_relation_2

        state_in = ops.testing.State(
            leader=True,
            relations=[relation_1, relation_2],
        )

        with ctx(ctx.on.relation_changed(relation_1), state_in) as manager:
            manager.charm.provider.update_config(path='/', scheme='https', listen_port=8443)

            relations = manager.charm.model.relations['http-endpoint']
            for rel in relations:
                assert rel.data[manager.charm.app] != {}
                assert '8443' in rel.data[manager.charm.app]['url']
                assert 'https' in rel.data[manager.charm.app]['url']
                assert manager.charm.config_changed_event_emitted is True

    def test_non_leader_does_not_publish(
        self,
        provider_charm_meta: dict[str, Any],
        provider_charm_relation_1: ops.testing.Relation,
        provider_charm_relation_2: ops.testing.Relation,
    ):
        """Test that non-leader units do not publish endpoint data."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation_1 = provider_charm_relation_1
        relation_2 = provider_charm_relation_2

        state_in = ops.testing.State(
            leader=False,
            relations=[relation_1, relation_2],
        )

        with ctx(ctx.on.relation_changed(relation_1), state_in) as manager:
            manager.run()

            # Non-leader should not update relation data
            relations = manager.charm.model.relations['http-endpoint']
            for rel in relations:
                assert rel.data[manager.charm.app] == {}

    def test_noop_when_no_relations(self, provider_charm_meta: dict[str, Any]):
        """Test that provider handles gracefully when there are no relations."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        state_in = ops.testing.State(
            leader=True,
            relations=[],
        )

        with ctx(ctx.on.config_changed(), state_in) as manager:
            manager.run()

            # Should not have any relations
            rel = manager.charm.model.relations['http-endpoint']
            assert len(rel) == 0

    def test_relation_broken(
        self,
        provider_charm_meta: dict[str, Any],
        provider_charm_relation_1: ops.testing.Relation,
        provider_charm_relation_2: ops.testing.Relation,
    ):
        """Test that provider handles relation broken events."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation_1 = provider_charm_relation_1
        relation_2 = provider_charm_relation_2

        state_in = ops.testing.State(
            leader=True,
            relations=[relation_1, relation_2],
        )

        with ctx(ctx.on.relation_broken(relation_1), state_in) as manager:
            manager.run()

            relations = manager.charm.model.relations['http-endpoint']
            assert len(relations) == 1


class TestHttpEndpointRequirer:
    """Tests for HttpEndpointRequirer."""

    def test_receives_endpoint_data(
        self,
        requirer_charm_meta: dict[str, Any],
        requirer_charm_relation_1: ops.testing.Relation,
        requirer_charm_relation_2: ops.testing.Relation,
    ):
        """Test that the requirer receives and parses endpoint data correctly."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation_1 = requirer_charm_relation_1
        relation_2 = requirer_charm_relation_2

        state_in = ops.testing.State(
            relations=[relation_1, relation_2],
        )

        with ctx(ctx.on.relation_changed(relation_1), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 2

            url_1 = HttpEndpointDataModel(url=HttpUrl('http://10.0.0.1:8080/'))
            url_2 = HttpEndpointDataModel(url=HttpUrl('https://10.0.0.2:8443/'))
            assert endpoints == [url_1, url_2]

    def test_charm_config_changed_receives_endpoint_data(
        self,
        requirer_charm_meta: dict[str, Any],
        requirer_charm_relation_1: ops.testing.Relation,
        requirer_charm_relation_2: ops.testing.Relation,
    ):
        """Test that the requirer receives and parses endpoint data correctly after configuring."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation_1 = requirer_charm_relation_1
        relation_2 = requirer_charm_relation_2

        state_in = ops.testing.State(
            relations=[relation_1, relation_2],
        )

        with ctx(ctx.on.config_changed(), state_in) as manager:
            manager.run()

            endpoints = manager.charm.endpoints
            assert len(endpoints) == 2

            url_1 = HttpEndpointDataModel(url=HttpUrl('http://10.0.0.1:8080/'))
            url_2 = HttpEndpointDataModel(url=HttpUrl('https://10.0.0.2:8443/'))
            assert endpoints == [url_1, url_2]

    def test_noop_when_no_relations(self, requirer_charm_meta: dict[str, Any]):
        """Test that requirer emits unavailable event when there are no relations."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        state_in = ops.testing.State(
            relations=[],
        )

        with ctx(ctx.on.start(), state_in) as manager:
            # Should be noop when there are no relations
            manager.run()
            assert len(manager.charm.endpoints) == 0
            assert manager.charm.available_event_emitted is False
            assert manager.charm.unavailable_event_emitted is False

    def test_handles_relation_broken(
        self,
        requirer_charm_meta: dict[str, Any],
        requirer_charm_relation_1: ops.testing.Relation,
        requirer_charm_relation_2: ops.testing.Relation,
    ):
        """Test that requirer handles relation broken events."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation_1 = requirer_charm_relation_1
        relation_2 = requirer_charm_relation_2

        state_in = ops.testing.State(
            relations=[relation_1, relation_2],
        )

        with ctx(ctx.on.relation_broken(relation_1), state_in) as manager:
            manager.run()

            # Should have one endpoint remaining after breaking one relation
            endpoints = manager.charm.endpoints
            assert len(endpoints) == 1

            url_2 = HttpEndpointDataModel(url=HttpUrl('https://10.0.0.2:8443/'))
            assert endpoints == [url_2]

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

            assert len(manager.charm.endpoints) == 0
            assert manager.charm.available_event_emitted is False
            assert manager.charm.unavailable_event_emitted is True

    def test_relation_with_no_app_data(self, requirer_charm_meta: dict[str, Any]):
        """Test that requirer handles relations where relation.app is None."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        # Create a relation without remote app
        relation = ops.testing.Relation(
            endpoint='http-endpoint',
            interface='http_endpoint',
        )

        state_in = ops.testing.State(
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            manager.run()

            # Should return empty list when relation.app is None
            endpoints = manager.charm.requirer.get_http_endpoints()
            assert len(endpoints) == 0
