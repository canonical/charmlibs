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
        self.framework.observe(
            self.provider.on.http_endpoint_config_required, self._on_config_required
        )

        self.provider_config: dict[str, Any] = {}

    def _on_config_required(self, _: ops.EventBase):
        """Record config required events."""
        if self.provider_config:
            self.provider.update_config(**self.provider_config)


class RequirerCharm(ops.CharmBase):
    """Test charm for HttpEndpointRequirer."""

    def __init__(self, *args: typing.Any):
        super().__init__(*args)
        self.requirer = HttpEndpointRequirer(self, 'http-endpoint')
        self.framework.observe(
            self.requirer.on.http_endpoint_available, self._on_endpoint_available
        )
        self.framework.observe(
            self.requirer.on.http_endpoint_unavailable, self._on_endpoint_unavailable
        )
        self.endpoints = []

    def _on_endpoint_available(self, _: ops.EventBase):
        """Record endpoint available events."""
        self.endpoints = self.requirer.http_endpoints

    def _on_endpoint_unavailable(self, _: ops.EventBase):
        """Record endpoint unavailable events."""
        self.endpoints = self.requirer.http_endpoints


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
            'scheme': 'http',
            'port': '8080',
            'hostname': '10.0.0.1',
        },
    )


@pytest.fixture
def requirer_charm_relation_2() -> ops.testing.Relation:
    """Return a relation for the RequirerCharm."""
    return ops.testing.Relation(
        endpoint='http-endpoint',
        interface='http_endpoint',
        remote_app_data={
            'scheme': 'https',
            'port': '8443',
            'hostname': '10.0.0.2',
        },
    )


@pytest.fixture
def provider_charm_relation() -> ops.testing.Relation:
    """Return a relation for the ProviderCharm."""
    return ops.testing.Relation(
        endpoint='http-endpoint',
        interface='http_endpoint',
    )
