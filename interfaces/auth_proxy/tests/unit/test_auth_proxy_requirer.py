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

"""Unit tests for AuthProxyRequirer."""

import json
import logging
from typing import Any

import ops.testing
import pytest
import yaml
from conftest import AUTH_PROXY_CONFIG
from ops.charm import CharmBase

from charmlibs.interfaces.auth_proxy import (
    AuthProxyConfig,
    AuthProxyRelationRemovedEvent,
    AuthProxyRequirer,
)

METADATA = """
name: requirer-tester
requires:
  auth-proxy:
    interface: auth_proxy
"""


class AuthProxyRequirerCharm(CharmBase):
    """Test charm for AuthProxyRequirer."""

    test_config: dict[str, Any] = AUTH_PROXY_CONFIG

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self.auth_proxy_config = AuthProxyConfig(**self.test_config) if self.test_config else None
        self.auth_proxy = AuthProxyRequirer(self, auth_proxy_config=self.auth_proxy_config)
        if self.auth_proxy_config:
            self.auth_proxy.update_auth_proxy_config(self.auth_proxy_config)


class TestAuthProxyRequirerIntegration:
    """Test suite for AuthProxyRequirer integration with Context."""

    @pytest.fixture
    def context(self) -> ops.testing.Context[AuthProxyRequirerCharm]:
        """Create a testing Context for the requirer charm."""
        AuthProxyRequirerCharm.test_config = AUTH_PROXY_CONFIG
        return ops.testing.Context(AuthProxyRequirerCharm, meta=yaml.safe_load(METADATA))

    def test_data_in_relation_bag(
        self,
        context: ops.testing.Context[AuthProxyRequirerCharm],
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that config data is properly serialized and placed in relation databag."""
        state_in = context.run(
            context.on.relation_created(auth_proxy_relation),
            ops.testing.State(relations=[auth_proxy_relation], leader=True),
        )

        rel_out = state_in.get_relation(auth_proxy_relation.id)
        rel_data = rel_out.local_app_data

        assert json.loads(rel_data['allowed_endpoints']) == AUTH_PROXY_CONFIG['allowed_endpoints']
        assert json.loads(rel_data['headers']) == AUTH_PROXY_CONFIG['headers']

    def test_warning_when_http_protected_url_provided(
        self,
        context: ops.testing.Context[AuthProxyRequirerCharm],
        auth_proxy_relation: ops.testing.Relation,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verifies that a warning log is raised when an insecure HTTP protected URL is used."""
        caplog.set_level(logging.WARNING)

        new_urls_config = ['https://some-url.com', 'http://some-other-url.com']
        AuthProxyRequirerCharm.test_config = {
            **AUTH_PROXY_CONFIG,
            'protected_urls': new_urls_config,
        }

        context.run(
            context.on.relation_created(auth_proxy_relation),
            ops.testing.State(leader=True, relations=[auth_proxy_relation]),
        )

        assert (
            f"Provided URL {new_urls_config[1]} uses http scheme. Don't do this in production"
            in caplog.text
        )

    def test_exception_raised_when_invalid_header(
        self,
        context: ops.testing.Context[AuthProxyRequirerCharm],
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that an exception is raised when invalid headers config is provided."""
        invalid_headers = ['X-Auth-Request-User', 'X-Invalid-Header']
        AuthProxyRequirerCharm.test_config = {**AUTH_PROXY_CONFIG, 'headers': invalid_headers}

        with pytest.raises(ops.testing.errors.UncaughtCharmError) as excinfo:
            context.run(
                context.on.start(),
                ops.testing.State(leader=True, relations=[auth_proxy_relation]),
            )

        assert 'Unsupported header' in str(excinfo.value)

    def test_auth_proxy_relation_removed_event_emitted(
        self,
        context: ops.testing.Context[AuthProxyRequirerCharm],
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthProxyRelationRemovedEvent is emitted on relation broken."""
        context.run(
            context.on.relation_broken(auth_proxy_relation),
            ops.testing.State(relations=[auth_proxy_relation], leader=True),
        )

        assert any(isinstance(e, AuthProxyRelationRemovedEvent) for e in context.emitted_events)
