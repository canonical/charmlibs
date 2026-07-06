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


def test_snap_error():
    err = _errors.Error(
        'the message',
        kind='the-kind',
        value='the-value',
        status_code=400,
        status='Bad Request',
    )
    # The message, kind and value are public.
    assert err.message == 'the message'
    assert err.kind == 'the-kind'
    assert err.value == 'the-value'
    # They're read-only properties, not attributes.
    with pytest.raises(AttributeError):
        err.message = ''  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        err.kind = ''  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        err.value = None  # pyright: ignore[reportAttributeAccessIssue]
    # Status code and status message aren't public.
    assert not hasattr(err, 'status_code')
    assert not hasattr(err, 'status')
    # The repr() contains *all* the arguments.
    r = repr(err)
    assert 'the message' in r
    assert 'the-kind' in r
    assert 'the-value' in r
    assert '400' in r
    assert 'Bad Request' in r
    # str() is just the message
    assert str(err) == 'the message'
