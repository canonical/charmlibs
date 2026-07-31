# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import builtins
import inspect

import pytest

from charmlibs.snap import _errors

# Error types in the module that are intentionally outside the snapd API error hierarchy.
_NON_API_ERROR_TYPES = frozenset({
    _errors.Error,
    _errors.BadResponseError,
    _errors.ConnectionError,
    _errors.SocketNotFoundError,
    _errors.TimeoutError,
})


@pytest.fixture(scope='module')
def error_types() -> frozenset[type[BaseException]]:
    """Every class defined in the _errors module, including private types."""
    return frozenset(
        obj
        for _, obj in inspect.getmembers(_errors, inspect.isclass)
        if obj.__module__ == _errors.__name__
    )


class TestErrorHierarchy:
    """Test that errors respect the semantic error hierarchy of the library.

    New error types will probably be specific snapd API errors, and should subclass APIError.
    This is what these tests expect by default. If a new error type is added elsewhere in the
    error hierarchy, it should be added to _NON_API_ERROR_TYPES, and other tests added as needed.
    """

    def test_all_error_types_subclass_error(self, error_types: frozenset[type[BaseException]]):
        for cls in error_types:
            assert issubclass(cls, _errors.Error)

    def test_api_error_subclasses(self, error_types: frozenset[type[BaseException]]):
        for cls in error_types - _NON_API_ERROR_TYPES:
            assert issubclass(cls, _errors.APIError)

    def test_non_api_error_subclasses(self):
        for cls in _NON_API_ERROR_TYPES:
            assert not issubclass(cls, _errors.APIError)

    def test_timeout_and_connection_errors_subclass_builtins(self):
        assert issubclass(_errors.TimeoutError, builtins.TimeoutError)
        assert issubclass(_errors.ConnectionError, builtins.ConnectionError)
        assert issubclass(_errors.SocketNotFoundError, builtins.ConnectionError)

    def test_socket_not_found_subclasses_connection_error(self):
        # Callers that only care that snapd was unreachable can catch ConnectionError.
        assert issubclass(_errors.SocketNotFoundError, _errors.ConnectionError)


def test_snap_error():
    err = _errors.Error('the message')
    # The message is the only public field.
    assert err.message == 'the message'
    # It's a read-only property, not an attribute.
    with pytest.raises(AttributeError):
        err.message = ''  # pyright: ignore[reportAttributeAccessIssue]
    # str() and repr() have nothing else to report.
    assert str(err) == 'the message'
    assert repr(err) == "charmlibs.snap._errors.Error('the message')"


def test_api_error():
    err = _errors.APIError(
        'the message',
        kind='the-kind',
        value='the-value',
        status_code=400,
        status='Bad Request',
    )
    # The message is public, as for any Error.
    assert err.message == 'the message'
    # The fields from the snapd error response are recorded privately, for logging and debugging.
    assert err._kind == 'the-kind'
    assert err._value == 'the-value'
    assert err._status_code == 400
    assert err._status == 'Bad Request'
    # The repr() contains *all* the arguments.
    r = repr(err)
    assert 'the message' in r
    assert 'the-kind' in r
    assert 'the-value' in r
    assert '400' in r
    assert 'Bad Request' in r
    # str() appends a string value that adds information the message doesn't already carry.
    assert str(err) == 'the message (the-value)'


@pytest.mark.parametrize('name', ['kind', 'value', 'status_code', 'status'])
def test_error_response_fields_are_not_public(name: str):
    # Only the message is public, on Error and APIError alike.
    assert not hasattr(_errors.Error('boom'), name)
    assert not hasattr(
        _errors.APIError('boom', kind='k', value='v', status_code=1, status='s'), name
    )


@pytest.mark.parametrize(
    ('message', 'value', 'expected'),
    [
        ('snap not installed', 'hello-world', 'snap not installed (hello-world)'),
        # Not appended when the value appears in the message.
        (
            'snap "hello-world" is not installed',
            'hello-world',
            'snap "hello-world" is not installed',
        ),
        ('boom', '', 'boom'),  # Not appended when the value is empty.
        # Not appended when the value is not a string.
        (
            'snap "lxd" has no "k" configuration option',
            {'SnapName': 'lxd', 'Key': 'k'},
            'snap "lxd" has no "k" configuration option',
        ),
    ],
)
def test_str_appends_informative_string_value(message: str, value: object, expected: str):
    assert str(_errors.APIError(message, kind='some-kind', value=value)) == expected


class TestTruncated:
    def test_short_detail_is_returned_whole(self):
        assert _errors._truncated('boom') == 'boom'

    def test_non_string_detail_is_stringified(self):
        assert _errors._truncated({'a': 1}) == "{'a': 1}"

    def test_long_detail_is_truncated_and_sized(self):
        detail = 'x' * (_errors._MAX_DETAIL + 1)
        truncated = _errors._truncated(detail)
        assert truncated.startswith('x' * _errors._MAX_DETAIL)
        assert not truncated.startswith(detail)
        assert str(len(detail)) in truncated
