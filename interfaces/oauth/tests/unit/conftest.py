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

"""Fixtures for unit tests, typically mocking out parts of the external system."""

from typing import Any

import pytest
import yaml
from ops.testing import Context


@pytest.fixture
def context(request: pytest.FixtureRequest) -> Context[Any]:
    """Fixture to dynamically generate the Context for either the provider or requirer charm."""
    module = getattr(request, 'module', None)
    module_name: str = getattr(module, '__name__', '') or ''
    if 'provider' in module_name:
        from tests.unit.test_oauth_provider import METADATA, OAuthProviderCharm

        return Context(OAuthProviderCharm, meta=yaml.safe_load(METADATA))
    else:
        from tests.unit.test_oauth_requirer import METADATA, OAuthRequirerCharm

        return Context(OAuthRequirerCharm, meta=yaml.safe_load(METADATA))


@pytest.fixture
def context_invalid_config() -> Context[Any]:
    """Fixture for context with invalid oauth configuration."""
    from tests.unit.test_oauth_requirer import METADATA, InvalidConfigOAuthRequirerCharm

    return Context(InvalidConfigOAuthRequirerCharm, meta=yaml.safe_load(METADATA))


@pytest.fixture
def provider_info() -> dict[str, str]:
    """Fixture for sample oauth provider information."""
    return {
        'authorization_endpoint': 'https://example.oidc.com/oauth2/auth',
        'introspection_endpoint': 'https://example.oidc.com/admin/oauth2/introspect',
        'issuer_url': 'https://example.oidc.com',
        'jwks_endpoint': 'https://example.oidc.com/.well-known/jwks.json',
        'scope': 'openid profile email phone',
        'token_endpoint': 'https://example.oidc.com/oauth2/token',
        'userinfo_endpoint': 'https://example.oidc.com/userinfo',
        'jwt_access_token': 'False',
    }
