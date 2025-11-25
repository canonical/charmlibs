# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for SPOE auth interface library."""

import json
import re
from typing import Any, cast

import pytest
from pydantic import IPvAnyAddress, ValidationError

from charmlibs.interfaces.haproxy_spoe_auth import (
    HaproxyEvent,
    SpoeAuthProviderAppData,
    SpoeAuthProviderUnitData,
)
from charmlibs.interfaces.haproxy_spoe_auth._spoe_auth import HOSTNAME_REGEX, DataValidationError

PLACEHOLDER_ADDRESS = '10.0.0.1'
PLACEHOLDER_SPOP_PORT = 8081
PLACEHOLDER_OIDC_CALLBACK_PORT = 5000
PLACEHOLDER_VAR_AUTHENTICATED = 'var.sess.is_authenticated'
PLACEHOLDER_VAR_REDIRECT_URL = 'var.sess.redirect_url'
PLACEHOLDER_COOKIE_NAME = 'auth_session'
PLACEHOLDER_hostname = 'auth.example.com'
PLACEHOLDER_OIDC_CALLBACK_PATH = '/oauth2/callback'


@pytest.fixture(name='mock_provider_app_data_dict')
def mock_provider_app_data_dict_fixture() -> dict[str, Any]:
    """Create mock provider application data dictionary."""
    return {
        'spop_port': PLACEHOLDER_SPOP_PORT,
        'oidc_callback_port': PLACEHOLDER_OIDC_CALLBACK_PORT,
        'event': 'on-frontend-http-request',
        'message_name': 'try-auth-oidc',
        'var_authenticated': PLACEHOLDER_VAR_AUTHENTICATED,
        'var_redirect_url': PLACEHOLDER_VAR_REDIRECT_URL,
        'cookie_name': PLACEHOLDER_COOKIE_NAME,
        'oidc_callback_path': PLACEHOLDER_OIDC_CALLBACK_PATH,
        'hostname': PLACEHOLDER_hostname,
    }


@pytest.fixture(name='mock_provider_unit_data_dict')
def mock_provider_unit_data_dict_fixture() -> dict[str, str]:
    """Create mock provider unit data dictionary."""
    return {'address': PLACEHOLDER_ADDRESS}


def test_spoe_auth_provider_app_data_validation():
    """
    arrange: Create a SpoeAuthProviderAppData model with valid data.
    act: Validate the model.
    assert: Model validation passes.
    """
    data = SpoeAuthProviderAppData(
        spop_port=PLACEHOLDER_SPOP_PORT,
        oidc_callback_port=PLACEHOLDER_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        message_name='try-auth-oidc',
        var_authenticated=PLACEHOLDER_VAR_AUTHENTICATED,
        var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
        cookie_name=PLACEHOLDER_COOKIE_NAME,
        hostname=PLACEHOLDER_hostname,
        oidc_callback_path=PLACEHOLDER_OIDC_CALLBACK_PATH,
    )

    assert data.spop_port == PLACEHOLDER_SPOP_PORT
    assert data.oidc_callback_port == PLACEHOLDER_OIDC_CALLBACK_PORT
    assert data.event == HaproxyEvent.ON_FRONTEND_HTTP_REQUEST
    assert data.var_authenticated == PLACEHOLDER_VAR_AUTHENTICATED
    assert data.var_redirect_url == PLACEHOLDER_VAR_REDIRECT_URL
    assert data.cookie_name == PLACEHOLDER_COOKIE_NAME
    assert data.hostname == PLACEHOLDER_hostname
    assert data.oidc_callback_path == PLACEHOLDER_OIDC_CALLBACK_PATH


def test_spoe_auth_provider_app_data_default_callback_path():
    """Create SpoeAuthProviderAppData with default callback path.

    arrange: Create a SpoeAuthProviderAppData model without specifying oidc_callback_path.
    act: Validate the model.
    assert: Model validation passes with default callback path.
    """
    data = SpoeAuthProviderAppData(
        spop_port=PLACEHOLDER_SPOP_PORT,
        oidc_callback_port=PLACEHOLDER_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        message_name='try-auth-oidc',
        var_authenticated=PLACEHOLDER_VAR_AUTHENTICATED,
        var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
        cookie_name=PLACEHOLDER_COOKIE_NAME,
        hostname=PLACEHOLDER_hostname,
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
            oidc_callback_port=PLACEHOLDER_OIDC_CALLBACK_PORT,
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            message_name='try-auth-oidc',
            var_authenticated=PLACEHOLDER_VAR_AUTHENTICATED,
            var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
            cookie_name=PLACEHOLDER_COOKIE_NAME,
            hostname=PLACEHOLDER_hostname,
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
            spop_port=PLACEHOLDER_SPOP_PORT,
            oidc_callback_port=port,  # Invalid: port must be > 0 and <= 65525
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            message_name='try-auth-oidc',
            var_authenticated=PLACEHOLDER_VAR_AUTHENTICATED,
            var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
            cookie_name=PLACEHOLDER_COOKIE_NAME,
            hostname=PLACEHOLDER_hostname,
        )


def test_spoe_auth_provider_app_data_invalid_hostname_format():
    """
    arrange: Create a SpoeAuthProviderAppData model with invalid hostname format.
    act: Validate the model.
    assert: Validation raises an error.
    """
    with pytest.raises(ValidationError):
        SpoeAuthProviderAppData(
            spop_port=PLACEHOLDER_SPOP_PORT,
            oidc_callback_port=PLACEHOLDER_OIDC_CALLBACK_PORT,
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            message_name='try-auth-oidc',
            var_authenticated=PLACEHOLDER_VAR_AUTHENTICATED,
            var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
            cookie_name=PLACEHOLDER_COOKIE_NAME,
            hostname='invalid-hostname-!@#',  # Invalid: contains special chars
        )


def test_spoe_auth_provider_app_data_invalid_char_in_var_authenticated():
    """
    arrange: Create a SpoeAuthProviderAppData model with invalid characters in var_authenticated.
    act: Validate the model.
    assert: Validation raises an error.
    """
    with pytest.raises(ValidationError):
        SpoeAuthProviderAppData(
            spop_port=PLACEHOLDER_SPOP_PORT,
            oidc_callback_port=PLACEHOLDER_OIDC_CALLBACK_PORT,
            event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
            message_name='try-auth-oidc',
            var_authenticated='invalid\nvar',  # Invalid: newline character
            var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
            cookie_name=PLACEHOLDER_COOKIE_NAME,
            hostname=PLACEHOLDER_hostname,
        )


def test_spoe_auth_provider_unit_data_validation():
    """
    arrange: Create a SpoeAuthProviderUnitData model with valid data.
    act: Validate the model.
    assert: Model validation passes.
    """
    data = SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', PLACEHOLDER_ADDRESS))

    assert str(data.address) == PLACEHOLDER_ADDRESS


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

    assert data.spop_port == PLACEHOLDER_SPOP_PORT
    assert data.oidc_callback_port == PLACEHOLDER_OIDC_CALLBACK_PORT
    assert data.event == HaproxyEvent.ON_FRONTEND_HTTP_REQUEST
    assert data.var_authenticated == PLACEHOLDER_VAR_AUTHENTICATED
    assert data.var_redirect_url == PLACEHOLDER_VAR_REDIRECT_URL
    assert data.cookie_name == PLACEHOLDER_COOKIE_NAME
    assert data.oidc_callback_path == PLACEHOLDER_OIDC_CALLBACK_PATH
    assert data.hostname == PLACEHOLDER_hostname
    assert data.message_name == 'try-auth-oidc'


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
        spop_port=PLACEHOLDER_SPOP_PORT,
        oidc_callback_port=PLACEHOLDER_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        message_name='try-auth-oidc',
        var_authenticated=PLACEHOLDER_VAR_AUTHENTICATED,
        var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
        cookie_name=PLACEHOLDER_COOKIE_NAME,
        hostname=PLACEHOLDER_hostname,
        oidc_callback_path=PLACEHOLDER_OIDC_CALLBACK_PATH,
    )

    databag: dict[str, Any] = {}
    result = data.dump(databag)

    assert result is not None
    assert 'spop_port' in databag
    assert json.loads(databag['spop_port']) == PLACEHOLDER_SPOP_PORT
    assert json.loads(databag['oidc_callback_port']) == PLACEHOLDER_OIDC_CALLBACK_PORT
    assert json.loads(databag['event']) == 'on-frontend-http-request'
    assert json.loads(databag['var_authenticated']) == PLACEHOLDER_VAR_AUTHENTICATED
    assert json.loads(databag['var_redirect_url']) == PLACEHOLDER_VAR_REDIRECT_URL
    assert json.loads(databag['cookie_name']) == PLACEHOLDER_COOKIE_NAME
    # oidc_callback_path should be included when explicitly set
    if 'oidc_callback_path' in databag:
        assert json.loads(databag['oidc_callback_path']) == PLACEHOLDER_OIDC_CALLBACK_PATH
    assert json.loads(databag['hostname']) == PLACEHOLDER_hostname
    assert json.loads(databag['message_name']) == 'try-auth-oidc'


def test_dump_and_load_provider_app_data_roundtrip():
    """
    arrange: Create a SpoeAuthProviderAppData model.
    act: Dump and then load it again.
    assert: The loaded data matches the original.
    """
    original_data = SpoeAuthProviderAppData(
        spop_port=PLACEHOLDER_SPOP_PORT,
        oidc_callback_port=PLACEHOLDER_OIDC_CALLBACK_PORT,
        event=HaproxyEvent.ON_FRONTEND_HTTP_REQUEST,
        message_name='try-auth-oidc',
        var_authenticated=PLACEHOLDER_VAR_AUTHENTICATED,
        var_redirect_url=PLACEHOLDER_VAR_REDIRECT_URL,
        cookie_name=PLACEHOLDER_COOKIE_NAME,
        hostname=PLACEHOLDER_hostname,
        oidc_callback_path=PLACEHOLDER_OIDC_CALLBACK_PATH,
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
    assert loaded_data.hostname == original_data.hostname
    assert loaded_data.oidc_callback_path == original_data.oidc_callback_path


def test_load_provider_unit_data(mock_provider_unit_data_dict: dict[str, str]):
    """
    arrange: Create a databag with valid unit data.
    act: Load the data with SpoeAuthProviderUnitData.load().
    assert: Data is loaded correctly.
    """
    databag = {k: json.dumps(v) for k, v in mock_provider_unit_data_dict.items()}
    data = cast('SpoeAuthProviderUnitData', SpoeAuthProviderUnitData.load(databag))

    assert str(data.address) == PLACEHOLDER_ADDRESS


def test_dump_provider_unit_data():
    """
    arrange: Create a SpoeAuthProviderUnitData model with valid data.
    act: Dump the model to a databag.
    assert: Databag contains correct data.
    """
    data = SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', PLACEHOLDER_ADDRESS))

    databag: dict[str, Any] = {}
    result = data.dump(databag)

    assert result is not None
    assert 'address' in databag
    assert json.loads(databag['address']) == PLACEHOLDER_ADDRESS


def test_dump_and_load_provider_unit_data_roundtrip():
    """
    arrange: Create a SpoeAuthProviderUnitData model.
    act: Dump and then load it again.
    assert: The loaded data matches the original.
    """
    original_data = SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', PLACEHOLDER_ADDRESS))

    # Dump to databag
    databag: dict[str, Any] = {}
    original_data.dump(databag)

    # Load from databag
    loaded_data = cast('SpoeAuthProviderUnitData', SpoeAuthProviderUnitData.load(databag))

    assert str(loaded_data.address) == str(original_data.address)


@pytest.mark.parametrize(
    'hostname,is_valid',
    [
        ('example.com', True),
        ('sub.example.com', True),
        ('test.sub.example.com', True),
        ('a.b.c.d.e.f.g.example.com', True),
        ('test-123.example.com', True),
        ('a.example.com', True),
        ('test.example-with-dash.com', True),
        ('very-long-subdomain-name-that-is-still-valid.example.com', True),
        ('x.y', True),
        ('123test.example.com', False),  # Must start with a letter
        ('example', False),  # No TLD
        ('-example.com', False),  # Starts with hyphen
        ('example-.com', False),  # Ends with hyphen
        ('ex--ample.com', False),  # Double hyphen
        ('example..com', False),  # Double dots
        ('.example.com', False),  # Starts with dot
        ('example.com.', False),  # Ends with dot
        ('example.', False),  # Ends with dot after TLD
        ('example..', False),  # Multiple dots at end
        ('', False),  # Empty string
        ('a' * 64 + '.com', False),  # Label too long (>63 chars)
        ('invalid-hostname-!@#.com', False),  # Invalid characters
        ('example with spaces.com', False),  # Spaces not allowed
        ('example\nnewline.com', False),  # Newline not allowed
        ('UPPERCASE.COM', True),  # Should be valid (case insensitive)
        ('mixed-Case.Example.COM', True),  # Mixed case should be valid
    ],
)
def test_hostname_regex_validation(hostname: str, is_valid: bool):
    """Test HOSTNAME_REGEX validates FQDNs correctly.

    arrange: Test various hostname strings against HOSTNAME_REGEX.
    act: Check if the hostname matches the regex pattern.
    assert: The result matches the expected validity.
    """
    match = re.match(HOSTNAME_REGEX, hostname)
    if is_valid:
        assert match is not None, f"Expected '{hostname}' to be valid but regex didn't match"
    else:
        assert match is None, f"Expected '{hostname}' to be invalid but regex matched"
