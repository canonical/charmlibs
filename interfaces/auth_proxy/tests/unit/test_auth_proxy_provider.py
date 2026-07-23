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

"""Unit tests for AuthProxyProvider."""

from typing import Any

import ops.testing
import pytest
import yaml
from ops.charm import CharmBase

from charmlibs.interfaces.auth_proxy import (
    AuthProxyConfigChangedEvent,
    AuthProxyConfigRemovedEvent,
    AuthProxyProvider,
)

METADATA = """
name: provider-tester
provides:
  auth-proxy:
    interface: auth_proxy
"""


class AuthProxyProviderCharm(CharmBase):
    """Test charm for AuthProxyProvider."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.auth_proxy = AuthProxyProvider(self)


class TestAuthProxyProviderIntegration:
    """Test suite for AuthProxyProvider integration with Context."""

    @pytest.fixture
    def context(self) -> ops.testing.Context[AuthProxyProviderCharm]:
        """Create a testing Context for the provider charm."""
        return ops.testing.Context(AuthProxyProviderCharm, meta=yaml.safe_load(METADATA))

    def test_auth_proxy_config_changed_event_emitted_when_relation_changed(
        self,
        context: ops.testing.Context[AuthProxyProviderCharm],
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthProxyConfigChangedEvent is emitted on valid relation changes."""
        context.run(
            context.on.relation_changed(auth_proxy_relation),
            ops.testing.State(leader=True, relations=[auth_proxy_relation]),
        )

        assert any(isinstance(e, AuthProxyConfigChangedEvent) for e in context.emitted_events)

    def test_auth_proxy_config_changed_event_not_emitted_when_invalid_config_provided(
        self,
        context: ops.testing.Context[AuthProxyProviderCharm],
    ) -> None:
        """Verifies that no success event is emitted if remote data is invalid."""
        relation = ops.testing.Relation(
            endpoint='auth-proxy',
            interface='auth_proxy',
            remote_app_name='requirer',
            remote_app_data={
                'allowed_endpoints': '["welcome", "about/app"]',
                'headers': '["X-User"]',
                'protected_urls': 'invalid-url',
            },
        )

        context.run(
            context.on.relation_changed(relation),
            ops.testing.State(leader=True, relations=[relation]),
        )

        assert not any(isinstance(e, AuthProxyConfigChangedEvent) for e in context.emitted_events)

    def test_auth_proxy_config_removed_event_emitted_when_relation_removed(
        self,
        context: ops.testing.Context[AuthProxyProviderCharm],
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthProxyConfigRemovedEvent is emitted on relation broken."""
        state_in = ops.testing.State(relations=[auth_proxy_relation], leader=True)
        context.run(context.on.relation_broken(auth_proxy_relation), state_in)

        assert any(isinstance(e, AuthProxyConfigRemovedEvent) for e in context.emitted_events)
