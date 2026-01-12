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
from unittest.mock import patch

import ops
import ops.testing
import pytest

from charmlibs.interfaces.http_endpoint._http_endpoint import (
    HttpEndpointInvalidDataError,
    _HttpEndpointDataModel,
)
from conftest import ProviderCharm, RequirerCharm


class TestHttpEndpointProvider:
    """Tests for HttpEndpointProvider."""

    def test_on_relation_changed_publish_default_endpoint(
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

        with patch('ops.Unit.set_ports') as mock_set_ports:
            with ctx(ctx.on.relation_changed(relation1), state_in) as manager:
                manager.run()

                # Both relations should have the data
                relations = manager.charm.model.relations['http-endpoint']
                assert len(relations) == 2
                assert mock_set_ports.call_count == 0  # Default does not set ports

                for rel in relations:
                    data = rel.load(_HttpEndpointDataModel, manager.charm.app)
                    assert data.url.port == 80  # Default port from provider init
                    assert data.url.scheme == 'http'  # Default scheme from provider init

    def test_update_config_with_valid_parameters(
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

        with patch('ops.Unit.set_ports') as mock_set_ports:
            with ctx(ctx.on.relation_changed(relation_1), state_in) as manager:
                manager.run()

                # Both relations should have the default data
                relations = manager.charm.model.relations['http-endpoint']
                assert len(relations) == 2
                assert mock_set_ports.call_count == 0  # Default does not set ports

                for rel in relations:
                    data = rel.load(_HttpEndpointDataModel, manager.charm.app)
                    assert data.url.port == 80  # Default port from provider init
                    assert data.url.scheme == 'http'  # Default scheme from provider init

                # Now update the config (e.g. performed by a charm author)
                manager.charm.provider.update_config(
                    path='/new', scheme='https', listen_port=8443, set_ports=True
                )
                relations = manager.charm.model.relations['http-endpoint']
                assert len(relations) == 2
                assert mock_set_ports.call_count == 1  # Ports should be set now
                for rel in relations:
                    data = rel.load(_HttpEndpointDataModel, manager.charm.app)
                    assert data.url.port == 8443  # New port
                    assert data.url.path == '/new'  # New path
                    assert data.url.scheme == 'https'  # New scheme

    @pytest.mark.parametrize(
        'path,scheme,listen_port',
        [
            ('/', 'ftp', 80),  # Invalid scheme
            ('/', 'http', -1),  # Invalid port (negative)
            ('/', 'http', 99999),  # Invalid port (too high)
        ],
    )
    def test_update_config_with_invalid_parameters(
        self,
        provider_charm_meta: dict[str, Any],
        provider_charm_relation_1: ops.testing.Relation,
        path: str,
        scheme: str,
        listen_port: int,
    ):
        """Test that update_config raises error with invalid parameters."""
        ctx = ops.testing.Context(
            ProviderCharm,
            meta=provider_charm_meta,
        )

        relation_1 = provider_charm_relation_1

        state_in = ops.testing.State(
            leader=True,
            relations=[relation_1],
        )

        with ctx(ctx.on.relation_changed(relation_1), state_in) as manager:
            manager.run()

            with pytest.raises(HttpEndpointInvalidDataError, match='Invalid http endpoint data'):
                manager.charm.provider.update_config(
                    path=path, scheme=scheme, listen_port=listen_port
                )

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

            # No relations should exist and thus no data to publish
            relations = manager.charm.model.relations['http-endpoint']
            assert len(relations) == 0


class TestHttpEndpointRequirer:
    """Tests for HttpEndpointRequirer."""

    def test_relation_changed_receives_endpoint_data(
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

            # Check that URLs are strings and have the expected values defined in conftest.py
            urls = manager.charm.requirer.get_urls()
            assert len(urls) == 6  # 3 units per relations (2 relations here)defined in conftest.py
            assert urls['remote_0/0'] == 'http://10.0.0.1:8080/'
            assert urls['remote_0/1'] == 'http://10.0.0.2:8080/'
            assert urls['remote_0/2'] == 'http://10.0.0.3:8080/'
            assert urls['remote_1/0'] == 'https://10.0.1.1:8443/'
            assert urls['remote_1/1'] == 'https://10.0.1.2:8443/'
            assert urls['remote_1/2'] == 'https://10.0.1.3:8443/'

            # Check that URLs are strings and have the expected values defined in conftest.py
            leader_urls = manager.charm.requirer.get_leader_urls()
            assert len(leader_urls) == 2
            assert 'http://10.0.0.1:8080/' in leader_urls
            assert 'https://10.0.1.1:8443/' in leader_urls

    def test_handle_invalid_relation_data(
        self,
        requirer_charm_meta: dict[str, Any],
        requirer_charm_relation_1: ops.testing.Relation,
    ):
        """Test that the requirer receives and parses endpoint data correctly."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        relation = requirer_charm_relation_1
        relation.remote_app_data.update({
            'url': '"invalid-url-format"',
        })

        state_in = ops.testing.State(
            relations=[relation],
        )

        with ctx(ctx.on.relation_changed(relation), state_in) as manager:
            manager.run()

            # Should return an empty list for invalid URL data
            urls = manager.charm.requirer.get_leader_urls()
            assert len(urls) == 0

    def test_no_relations_returns_no_endpoint_data(self, requirer_charm_meta: dict[str, Any]):
        """Test that the requirer handles no relations gracefully."""
        ctx = ops.testing.Context(
            RequirerCharm,
            meta=requirer_charm_meta,
        )

        state_in = ops.testing.State(
            relations=[],
        )

        with ctx(ctx.on.start(), state_in) as manager:
            manager.run()

            # Should return an empty list when there are no relations
            assert len(manager.charm.requirer.get_urls()) == 0
            assert len(manager.charm.requirer.get_leader_urls()) == 0
