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

"""Fixtures for unit tests, typically mocking out parts of the external system."""

import typing
from typing import Any

import ops
import ops.testing
import pytest

from charmlibs.interfaces.http_endpoint._http_endpoint import (
    HttpEndpointProvider,
    HttpEndpointRequirer,
)


class ProviderCharm(ops.CharmBase):
    """Test charm for HttpEndpointProvider."""

    def __init__(self, *args: typing.Any):
        super().__init__(*args)
        self.provider = HttpEndpointProvider(self, 'http-endpoint')


class RequirerCharm(ops.CharmBase):
    """Test charm for HttpEndpointRequirer."""

    def __init__(self, *args: typing.Any):
        super().__init__(*args)
        self.requirer = HttpEndpointRequirer(self, 'http-endpoint')


@pytest.fixture
def provider_charm_meta() -> dict[str, Any]:
    """Return the metadata for the ProviderCharm."""
    return {
        'name': 'provider-charm',
        'provides': {'http-endpoint': {'interface': 'http_endpoint'}},
    }


@pytest.fixture
def requirer_charm_meta() -> dict[str, Any]:
    """Return the metadata for the RequirerCharm."""

    return {
        'name': 'requirer-charm',
        'requires': {'http-endpoint': {'interface': 'http_endpoint'}},
    }


@pytest.fixture
def requirer_charm_relation_1() -> ops.testing.Relation:
    """Return a relation for the RequirerCharm."""
    return ops.testing.Relation(
        endpoint='http-endpoint',
        interface='http_endpoint',
        remote_app_data={
            'url': '"http://10.0.0.1:8080/"',
        },
    )


@pytest.fixture
def requirer_charm_relation_2() -> ops.testing.Relation:
    """Return a relation for the RequirerCharm."""
    return ops.testing.Relation(
        endpoint='http-endpoint',
        interface='http_endpoint',
        remote_app_data={
            'url': '"https://10.0.0.2:8443/"',
        },
    )


@pytest.fixture
def provider_charm_relation_1() -> ops.testing.Relation:
    """Return a relation for the ProviderCharm."""
    return ops.testing.Relation(
        endpoint='http-endpoint',
        interface='http_endpoint',
    )


@pytest.fixture
def provider_charm_relation_2() -> ops.testing.Relation:
    """Return a relation for the ProviderCharm."""
    return ops.testing.Relation(
        endpoint='http-endpoint',
        interface='http_endpoint',
    )
