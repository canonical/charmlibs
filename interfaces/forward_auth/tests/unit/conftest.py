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

import json
from typing import Any

import pytest
import yaml
from ops.testing import Context, Relation

FORWARD_AUTH_CONFIG = {
    'decisions_address': 'https://oauth2-proxy-k8s.testing.svc.cluster.local:4180',
    'app_names': ['charmed-app'],
    'headers': ['X-Auth-Request-User'],
}

FORWARD_AUTH_REQUIRER_CONFIG = {
    'ingress_app_names': ['charmed-app'],
}


def dict_to_relation_data(dic: dict[str, Any]) -> dict[str, str]:
    """Helper function to serialize a dictionary to relation data format."""
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


@pytest.fixture
def context(request: pytest.FixtureRequest) -> Context[Any]:
    """Fixture to dynamically generate the Context for either the provider or requirer charm."""
    module = getattr(request, 'module', None)
    module_name: str = getattr(module, '__name__', '') or ''
    if 'provider' in module_name:
        from test_forward_auth_provider import (
            METADATA,
            ForwardAuthProviderCharm,
        )

        return Context(ForwardAuthProviderCharm, meta=yaml.safe_load(METADATA))
    else:
        from test_forward_auth_requirer import (
            METADATA,
            ForwardAuthRequirerCharm,
        )

        return Context(ForwardAuthRequirerCharm, meta=yaml.safe_load(METADATA))


@pytest.fixture
def forward_auth_relation() -> Relation:
    """Fixture to provide a Relation in a provider context."""
    return Relation(
        endpoint='forward-auth',
        interface='forward_auth',
        remote_app_name='traefik',
        local_app_data=dict_to_relation_data(FORWARD_AUTH_CONFIG),
        remote_app_data=dict_to_relation_data(FORWARD_AUTH_REQUIRER_CONFIG),
    )


@pytest.fixture
def forward_auth_relation_requirer() -> Relation:
    """Fixture to provide a Relation in a requirer context."""
    return Relation(
        endpoint='forward-auth',
        interface='forward_auth',
        remote_app_data=dict_to_relation_data(FORWARD_AUTH_CONFIG),
        local_app_data=dict_to_relation_data(FORWARD_AUTH_REQUIRER_CONFIG),
    )
