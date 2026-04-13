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

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from charmlibs.interfaces.istio_ingress_config import (
    IngressConfigProvider,
    IngressConfigRequirer,
    ProviderIngressConfigData,
)
from charmlibs.interfaces.istio_ingress_config._istio_ingress_config import (
    FAKE_EXT_AUTHZ_PORT,
    FAKE_EXT_AUTHZ_SERVICE_NAME,
)


@pytest.fixture
def mock_app() -> MagicMock:
    app = MagicMock()
    app.name = 'test-app'
    return app


@pytest.fixture
def mock_relation(mock_app: MagicMock) -> MagicMock:
    relation = MagicMock()
    relation.app = MagicMock()
    relation.app.name = 'remote-app'
    relation.data = {mock_app: {}, relation.app: {}}
    return relation


@pytest.fixture
def mock_relation_mapping(mock_relation: MagicMock) -> MagicMock:
    mapping = MagicMock()
    mapping.get.return_value = [mock_relation]
    return mapping


def test_provider_publish(
    mock_relation_mapping: MagicMock,
    mock_app: MagicMock,
    mock_relation: MagicMock,
) -> None:
    """Provider publishes ext_authz config to all relations."""
    provider = IngressConfigProvider(mock_relation_mapping, mock_app)
    provider.publish(ext_authz_service_name='my-service', ext_authz_port='8080')

    databag = mock_relation.data[mock_app]
    assert databag['ext_authz_service_name'] == 'my-service'
    assert databag['ext_authz_port'] == '8080'


def test_provider_publish_with_headers(
    mock_relation_mapping: MagicMock,
    mock_app: MagicMock,
    mock_relation: MagicMock,
) -> None:
    """Provider publishes header config as JSON-serialized strings."""
    provider = IngressConfigProvider(mock_relation_mapping, mock_app)
    provider.publish(
        ext_authz_service_name='svc',
        ext_authz_port='9090',
        include_headers_in_check=['authorization', 'cookie'],
    )

    databag = mock_relation.data[mock_app]
    assert json.loads(databag['include_headers_in_check']) == ['authorization', 'cookie']


def test_provider_clear_publishes_fake_config(
    mock_relation_mapping: MagicMock,
    mock_app: MagicMock,
    mock_relation: MagicMock,
) -> None:
    """Provider clear() publishes fake config as a workaround for juju databag clearing bug."""
    provider = IngressConfigProvider(mock_relation_mapping, mock_app)
    provider.clear()

    databag = mock_relation.data[mock_app]
    assert databag['ext_authz_service_name'] == FAKE_EXT_AUTHZ_SERVICE_NAME
    assert databag['ext_authz_port'] == FAKE_EXT_AUTHZ_PORT


def test_provider_get_ext_authz_provider_name(
    mock_relation_mapping: MagicMock,
    mock_app: MagicMock,
    mock_relation: MagicMock,
) -> None:
    """Provider reads the ext_authz_provider_name from the requirer's databag."""
    mock_relation.data[mock_relation.app] = {'ext_authz_provider_name': 'ext_authz-test-abc123'}
    provider = IngressConfigProvider(mock_relation_mapping, mock_app)

    assert provider.get_ext_authz_provider_name() == 'ext_authz-test-abc123'
    assert provider.is_ready() is True


def test_provider_not_ready_when_no_relations(mock_app: MagicMock) -> None:
    """Provider is not ready when there are no relations."""
    mapping = MagicMock()
    mapping.get.return_value = []
    provider = IngressConfigProvider(mapping, mock_app)

    assert provider.get_ext_authz_provider_name() is None
    assert provider.is_ready() is False


def test_requirer_get_provider_ext_authz_info(
    mock_relation_mapping: MagicMock,
    mock_app: MagicMock,
    mock_relation: MagicMock,
) -> None:
    """Requirer reads and deserializes the provider's ext_authz configuration."""
    mock_relation.data[mock_relation.app] = {
        'ext_authz_service_name': 'authz-svc',
        'ext_authz_port': '8080',
        'include_headers_in_check': json.dumps(['authorization']),
    }
    requirer = IngressConfigRequirer(mock_relation_mapping, mock_app)
    info = requirer.get_provider_ext_authz_info(mock_relation)

    assert info is not None
    assert info.ext_authz_service_name == 'authz-svc'
    assert info.ext_authz_port == '8080'
    assert info.include_headers_in_check == ['authorization']


def test_requirer_detects_fake_authz_config(
    mock_relation_mapping: MagicMock,
    mock_app: MagicMock,
    mock_relation: MagicMock,
) -> None:
    """Requirer detects fake authz config published by provider clear()."""
    mock_relation.data[mock_relation.app] = {
        'ext_authz_service_name': FAKE_EXT_AUTHZ_SERVICE_NAME,
        'ext_authz_port': FAKE_EXT_AUTHZ_PORT,
    }
    requirer = IngressConfigRequirer(mock_relation_mapping, mock_app)

    assert requirer.is_fake_authz_config(mock_relation) is True


def test_port_validation() -> None:
    """Port field rejects non-integer strings."""
    with pytest.raises(ValueError, match='convertible to an integer'):
        ProviderIngressConfigData(ext_authz_port='not-a-number')
