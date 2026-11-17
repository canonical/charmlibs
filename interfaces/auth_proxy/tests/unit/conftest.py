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

"""Fixtures and test configuration for unit tests."""

import json
from typing import Any

import ops.testing
import pytest

AUTH_PROXY_CONFIG = {
    'protected_urls': ['https://example.com'],
    'allowed_endpoints': ['welcome', 'about/app'],
    'headers': ['X-Auth-Request-User'],
    'authenticated_emails': ['test@canonical.com'],
    'authenticated_email_domains': ['example.com'],
}


def dict_to_relation_data(dic: dict[str, Any]) -> dict[str, str]:
    """Helper to convert dictionary lists/dicts to JSON strings."""
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


@pytest.fixture
def auth_proxy_relation() -> ops.testing.Relation:
    """Fixture that represents an active auth-proxy relation."""
    return ops.testing.Relation(
        endpoint='auth-proxy',
        interface='auth_proxy',
        remote_app_name='requirer',
        remote_app_data=dict_to_relation_data(AUTH_PROXY_CONFIG),
    )
