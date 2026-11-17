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


class TestBadResponseError:
    """BadResponseError carries what snapd sent, for the caller to put in a bug report."""

    def test_response_is_not_public(self):
        # It's only there for the repr: a caller can't do anything with it but report it.
        err = _errors.BadResponseError('boom', response={'unexpected': 'shape'})
        assert not hasattr(err, 'response')
        assert err._response == {'unexpected': 'shape'}

    def test_response_defaults_to_none(self):
        # Not every bad response has anything to report beyond the message.
        assert _errors.BadResponseError('boom')._response is None

    def test_str_appends_the_response(self):
        # str() is what a traceback shows, and is the only channel that reaches a bug report
        # when a charm doesn't catch the error.
        err = _errors.BadResponseError('boom', response='oops')
        assert str(err) == "boom -- response:\n'oops'"

    def test_str_is_just_the_message_without_a_response(self):
        assert str(_errors.BadResponseError('boom')) == 'boom'

    @pytest.mark.parametrize(
        'response',
        [
            'oops',  # A string is quoted, so an empty or padded body is still visible.
            '',
            {'unexpected': 'shape'},
            ['hello-world'],
            b'not json at all',
        ],
    )
    def test_str_renders_the_response_with_repr(self, response: object):
        # repr(), not str(): it escapes control characters that would otherwise mangle a
        # terminal, and keeps the difference between a string and a decoded JSON value visible.
        err = _errors.BadResponseError('boom', response=response)
        assert str(err) == f'boom -- response:\n{response!r}'

    def test_str_escapes_control_characters_in_the_response(self):
        err = _errors.BadResponseError('boom', response='a\nb\x00c')
        assert '\\n' in str(err)  # The newline is escaped, not emitted raw.
        assert str(err).count('\n') == 1  # Only the separator before the response.

    def test_message_stays_clean_for_a_charm_status(self):
        # A charm putting the error in its status wants the message, not the whole body.
        err = _errors.BadResponseError('boom', response='oops' * 100)
        assert err.message == 'boom'

    @pytest.mark.parametrize('response', ['oops', {'unexpected': 'shape'}, ''])
    def test_repr_contains_the_message_and_the_response(self, response: object):
        r = repr(_errors.BadResponseError('boom', response=response))
        assert r == f"charmlibs.snap._errors.BadResponseError('boom', response={response!r})"

    def test_repr_doesnt_contain_a_none_response(self):
        r = repr(_errors.BadResponseError('boom', response=None))
        assert r == "charmlibs.snap._errors.BadResponseError('boom')"
