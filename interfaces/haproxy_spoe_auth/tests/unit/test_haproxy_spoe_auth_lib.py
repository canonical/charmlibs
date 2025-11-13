# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for SPOE auth interface library."""

import json
from typing import Any, cast

import pytest
from pydantic import IPvAnyAddress, ValidationError

from charmlibs.interfaces.haproxy_spoe_auth import (
    HaproxyEvent,
    SpoeAuthProviderAppData,
    SpoeAuthProviderUnitData,
)
from charmlibs.interfaces.haproxy_spoe_auth._spoe_auth import DataValidationError

MOCK_ADDRESS = '10.0.0.1'
MOCK_SPOP_PORT = 8081
MOCK_OIDC_CALLBACK_PORT = 5000
MOCK_VAR_AUTHENTICATED = 'var.sess.is_authenticated'
MOCK_VAR_REDIRECT_URL = 'var.sess.redirect_url'
MOCK_COOKIE_NAME = 'auth_session'
MOCK_OIDC_CALLBACK_HOSTNAME = 'auth.example.com'
MOCK_OIDC_CALLBACK_PATH = '/oauth2/callback'


@pytest.fixture(name='mock_provider_app_data_dict')
def mock_provider_app_data_dict_fixture() -> dict[str, Any]:
    """Create mock provider application data dictionary."""
    return {
        'spop_port': MOCK_SPOP_PORT,
        'oidc_callback_port': MOCK_OIDC_CALLBACK_PORT,
        'event': 'on-frontend-http-request',
        'var_authenticated': MOCK_VAR_AUTHENTICATED,
        'var_redirect_url': MOCK_VAR_REDIRECT_URL,
        'cookie_name': MOCK_COOKIE_NAME,
        'oidc_callback_path': MOCK_OIDC_CALLBACK_PATH,
        'oidc_callback_hostname': MOCK_OIDC_CALLBACK_HOSTNAME,
    }


@pytest.fixture(name='mock_provider_unit_data_dict')
def mock_provider_unit_data_dict_fixture() -> dict[str, str]:
    """Create mock provider unit data dictionary."""
    return {'address': MOCK_ADDRESS}


def test_spoe_auth_provider_app_data_validation():
    """
    arrange: Create a SpoeAuthProviderAppData model with valid data.
    act: Validate the model.
    assert: Model validation passes.
    """
    data = SpoeAuthProviderAppData(
        spop_port=MOCK_SPOP_PORT,
        oidc_callback_port=MOCK_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        var_authenticated=MOCK_VAR_AUTHENTICATED,
        var_redirect_url=MOCK_VAR_REDIRECT_URL,
        cookie_name=MOCK_COOKIE_NAME,
        oidc_callback_hostname=MOCK_OIDC_CALLBACK_HOSTNAME,
        oidc_callback_path=MOCK_OIDC_CALLBACK_PATH,
    )

    assert data.spop_port == MOCK_SPOP_PORT
    assert data.oidc_callback_port == MOCK_OIDC_CALLBACK_PORT
    assert data.event == HaproxyEvent.ON_FRONTEND_HTTP_REQUEST
    assert data.var_authenticated == MOCK_VAR_AUTHENTICATED
    assert data.var_redirect_url == MOCK_VAR_REDIRECT_URL
    assert data.cookie_name == MOCK_COOKIE_NAME
    assert data.oidc_callback_hostname == MOCK_OIDC_CALLBACK_HOSTNAME
    assert data.oidc_callback_path == MOCK_OIDC_CALLBACK_PATH


def test_spoe_auth_provider_app_data_default_callback_path():
    """Create SpoeAuthProviderAppData with default callback path.

    arrange: Create a SpoeAuthProviderAppData model without specifying oidc_callback_path.
    act: Validate the model.
    assert: Model validation passes with default callback path.
    """
    data = SpoeAuthProviderAppData(
        spop_port=MOCK_SPOP_PORT,
        oidc_callback_port=MOCK_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        var_authenticated=MOCK_VAR_AUTHENTICATED,
        var_redirect_url=MOCK_VAR_REDIRECT_URL,
        cookie_name=MOCK_COOKIE_NAME,
        oidc_callback_hostname=MOCK_OIDC_CALLBACK_HOSTNAME,
        oidc_callback_path='/oauth2/callback',  # Explicitly set to the default value
    )

    assert data.oidc_callback_path == '/oauth2/callback'


@pytest.mark.parametrize('port', [0, 65526])
def test_spoe_auth_provider_app_data_invalid_spop_port(port: int):
    """
    arrange: Create a SpoeAuthProviderAppData model with spop_port set to 0.
    act: Validate the model.
    assert: Validation raises an error.
    """
    with pytest.raises(ValidationError):
        SpoeAuthProviderAppData(
            spop_port=port,  # Invalid: port must be > 0 and <= 65525
            oidc_callback_port=MOCK_OIDC_CALLBACK_PORT,
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            var_authenticated=MOCK_VAR_AUTHENTICATED,
            var_redirect_url=MOCK_VAR_REDIRECT_URL,
            cookie_name=MOCK_COOKIE_NAME,
            oidc_callback_hostname=MOCK_OIDC_CALLBACK_HOSTNAME,
        )


@pytest.mark.parametrize('port', [0, 65526])
def test_spoe_auth_provider_app_data_invalid_oidc_callback_port(port: int):
    """
    arrange: Create a SpoeAuthProviderAppData model with invalid oidc_callback_port.
    act: Validate the model.
    assert: Validation raises an error.
    """
    with pytest.raises(ValidationError):
        SpoeAuthProviderAppData(
            spop_port=MOCK_SPOP_PORT,
            oidc_callback_port=port,  # Invalid: port must be > 0 and <= 65525
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            var_authenticated=MOCK_VAR_AUTHENTICATED,
            var_redirect_url=MOCK_VAR_REDIRECT_URL,
            cookie_name=MOCK_COOKIE_NAME,
            oidc_callback_hostname=MOCK_OIDC_CALLBACK_HOSTNAME,
        )


def test_spoe_auth_provider_app_data_invalid_hostname_format():
    """
    arrange: Create a SpoeAuthProviderAppData model with invalid hostname format.
    act: Validate the model.
    assert: Validation raises an error.
    """
    with pytest.raises(ValidationError):
        SpoeAuthProviderAppData(
            spop_port=MOCK_SPOP_PORT,
            oidc_callback_port=MOCK_OIDC_CALLBACK_PORT,
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            var_authenticated=MOCK_VAR_AUTHENTICATED,
            var_redirect_url=MOCK_VAR_REDIRECT_URL,
            cookie_name=MOCK_COOKIE_NAME,
            oidc_callback_hostname='invalid-hostname-!@#',  # Invalid: contains special chars
        )


def test_spoe_auth_provider_app_data_invalid_char_in_var_authenticated():
    """
    arrange: Create a SpoeAuthProviderAppData model with invalid characters in var_authenticated.
    act: Validate the model.
    assert: Validation raises an error.
    """
    with pytest.raises(ValidationError):
        SpoeAuthProviderAppData(
            spop_port=MOCK_SPOP_PORT,
            oidc_callback_port=MOCK_OIDC_CALLBACK_PORT,
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            var_authenticated='invalid\nvar',  # Invalid: newline character
            var_redirect_url=MOCK_VAR_REDIRECT_URL,
            cookie_name=MOCK_COOKIE_NAME,
            oidc_callback_hostname=MOCK_OIDC_CALLBACK_HOSTNAME,
        )


def test_spoe_auth_provider_unit_data_validation():
    """
    arrange: Create a SpoeAuthProviderUnitData model with valid data.
    act: Validate the model.
    assert: Model validation passes.
    """
    data = SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', MOCK_ADDRESS))

    assert str(data.address) == MOCK_ADDRESS


def test_spoe_auth_provider_unit_data_ipv6_validation():
    """
    arrange: Create a SpoeAuthProviderUnitData model with IPv6 address.
    act: Validate the model.
    assert: Model validation passes.
    """
    ipv6_address = '2001:db8::1'
    data = SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', ipv6_address))

    assert str(data.address) == ipv6_address


def test_spoe_auth_provider_unit_data_invalid_address():
    """
    arrange: Create a SpoeAuthProviderUnitData model with invalid IP address.
    act: Validate the model.
    assert: Validation raises an error.
    """
    with pytest.raises(ValidationError):
        SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', 'invalid-ip-address'))


def test_load_provider_app_data(mock_provider_app_data_dict: dict[str, Any]):
    """
    arrange: Create a databag with valid provider application data.
    act: Load the data with SpoeAuthProviderAppData.load().
    assert: Data is loaded correctly.
    """
    databag = {k: json.dumps(v) for k, v in mock_provider_app_data_dict.items()}
    data = cast('SpoeAuthProviderAppData', SpoeAuthProviderAppData.load(databag))

    assert data.spop_port == MOCK_SPOP_PORT
    assert data.oidc_callback_port == MOCK_OIDC_CALLBACK_PORT
    assert data.event == HaproxyEvent.ON_FRONTEND_HTTP_REQUEST
    assert data.var_authenticated == MOCK_VAR_AUTHENTICATED
    assert data.var_redirect_url == MOCK_VAR_REDIRECT_URL
    assert data.cookie_name == MOCK_COOKIE_NAME
    assert data.oidc_callback_path == MOCK_OIDC_CALLBACK_PATH
    assert data.oidc_callback_hostname == MOCK_OIDC_CALLBACK_HOSTNAME


def test_load_provider_app_data_invalid_databag():
    """
    arrange: Create a databag with invalid JSON.
    act: Load the data with SpoeAuthProviderAppData.load().
    assert: DataValidationError is raised.
    """
    invalid_databag = {
        'spop_port': 'not-json',
    }
    with pytest.raises(DataValidationError):
        SpoeAuthProviderAppData.load(invalid_databag)


def test_dump_provider_app_data():
    """Dump provider app data to databag.

    arrange: Create a SpoeAuthProviderAppData model with valid data.
    act: Dump the model to a databag.
    assert: Databag contains correct data.
    """
    data = SpoeAuthProviderAppData(
        spop_port=MOCK_SPOP_PORT,
        oidc_callback_port=MOCK_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        var_authenticated=MOCK_VAR_AUTHENTICATED,
        var_redirect_url=MOCK_VAR_REDIRECT_URL,
        cookie_name=MOCK_COOKIE_NAME,
        oidc_callback_hostname=MOCK_OIDC_CALLBACK_HOSTNAME,
        oidc_callback_path=MOCK_OIDC_CALLBACK_PATH,
    )

    databag: dict[str, Any] = {}
    result = data.dump(databag)

    assert result is not None
    assert 'spop_port' in databag
    assert json.loads(databag['spop_port']) == MOCK_SPOP_PORT
    assert json.loads(databag['oidc_callback_port']) == MOCK_OIDC_CALLBACK_PORT
    assert json.loads(databag['event']) == 'on-frontend-http-request'
    assert json.loads(databag['var_authenticated']) == MOCK_VAR_AUTHENTICATED
    assert json.loads(databag['var_redirect_url']) == MOCK_VAR_REDIRECT_URL
    assert json.loads(databag['cookie_name']) == MOCK_COOKIE_NAME
    # oidc_callback_path should be included when explicitly set
    if 'oidc_callback_path' in databag:
        assert json.loads(databag['oidc_callback_path']) == MOCK_OIDC_CALLBACK_PATH
    assert json.loads(databag['oidc_callback_hostname']) == MOCK_OIDC_CALLBACK_HOSTNAME


def test_dump_and_load_provider_app_data_roundtrip():
    """
    arrange: Create a SpoeAuthProviderAppData model.
    act: Dump and then load it again.
    assert: The loaded data matches the original.
    """
    original_data = SpoeAuthProviderAppData(
        spop_port=MOCK_SPOP_PORT,
        oidc_callback_port=MOCK_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        var_authenticated=MOCK_VAR_AUTHENTICATED,
        var_redirect_url=MOCK_VAR_REDIRECT_URL,
        cookie_name=MOCK_COOKIE_NAME,
        oidc_callback_hostname=MOCK_OIDC_CALLBACK_HOSTNAME,
        oidc_callback_path=MOCK_OIDC_CALLBACK_PATH,
    )

    # Dump to databag
    databag: dict[str, Any] = {}
    original_data.dump(databag)

    # Load from databag
    loaded_data = cast('SpoeAuthProviderAppData', SpoeAuthProviderAppData.load(databag))

    assert loaded_data.spop_port == original_data.spop_port
    assert loaded_data.oidc_callback_port == original_data.oidc_callback_port
    assert loaded_data.event == original_data.event
    assert loaded_data.var_authenticated == original_data.var_authenticated
    assert loaded_data.var_redirect_url == original_data.var_redirect_url
    assert loaded_data.cookie_name == original_data.cookie_name
    assert loaded_data.oidc_callback_hostname == original_data.oidc_callback_hostname
    assert loaded_data.oidc_callback_path == original_data.oidc_callback_path


def test_load_provider_unit_data(mock_provider_unit_data_dict: dict[str, str]):
    """
    arrange: Create a databag with valid unit data.
    act: Load the data with SpoeAuthProviderUnitData.load().
    assert: Data is loaded correctly.
    """
    databag = {k: json.dumps(v) for k, v in mock_provider_unit_data_dict.items()}
    data = cast('SpoeAuthProviderUnitData', SpoeAuthProviderUnitData.load(databag))

    assert str(data.address) == MOCK_ADDRESS


def test_dump_provider_unit_data():
    """
    arrange: Create a SpoeAuthProviderUnitData model with valid data.
    act: Dump the model to a databag.
    assert: Databag contains correct data.
    """
    data = SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', MOCK_ADDRESS))

    databag: dict[str, Any] = {}
    result = data.dump(databag)

    assert result is not None
    assert 'address' in databag
    assert json.loads(databag['address']) == MOCK_ADDRESS


def test_dump_and_load_provider_unit_data_roundtrip():
    """
    arrange: Create a SpoeAuthProviderUnitData model.
    act: Dump and then load it again.
    assert: The loaded data matches the original.
    """
    original_data = SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', MOCK_ADDRESS))

    # Dump to databag
    databag: dict[str, Any] = {}
    original_data.dump(databag)

    # Load from databag
    loaded_data = cast('SpoeAuthProviderUnitData', SpoeAuthProviderUnitData.load(databag))

    assert str(loaded_data.address) == str(original_data.address)
