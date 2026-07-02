#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_conf: get, set, unset."""

from __future__ import annotations

from typing import Any

import pytest

from charmlibs.snap import _errors, _snapd_conf
from conftest import ensure_installed

_SNAP = 'lxd'
# A key prefix we use to avoid colliding with real lxd configuration.
_KEY = 'test-functional-key'
_KEY2 = 'test-functional-key2'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# Test helper and possible future candidate for library public API.
def _get_one(snap: str, key: str, /) -> Any:
    """Get a single snap configuration key."""
    config = _snapd_conf.get(snap, key)
    return config[key]


def _cleanup(*keys: str) -> None:
    """Unset test keys to avoid contaminating other tests."""
    _snapd_conf.unset(_SNAP, _KEY, *keys)


# ---------------------------------------------------------------------------
# set and get roundtrip
# ---------------------------------------------------------------------------


def test_set_and_get_bool_true():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: True})
    assert _get_one(_SNAP, _KEY) is True
    _cleanup()


def test_set_and_get_bool_false():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: False})
    assert _get_one(_SNAP, _KEY) is False
    _cleanup()


def test_set_and_get_integer():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 42})
    assert _get_one(_SNAP, _KEY) == 42
    _cleanup()


def test_set_and_get_float():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 3.14})
    assert _get_one(_SNAP, _KEY) == 3.14
    _cleanup()


def test_set_and_get_string():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _get_one(_SNAP, _KEY) == 'hello'
    _cleanup()


def test_set_and_get_list():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: [1, 2, 3]})
    assert _get_one(_SNAP, _KEY) == [1, 2, 3]
    _cleanup()


def test_set_and_get_dict():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: {'a': 1, 'b': 'two'}})
    assert _get_one(_SNAP, _KEY) == {'a': 1, 'b': 'two'}
    # Dotted notation reads back a single nested value.
    assert _get_one(_SNAP, f'{_KEY}.a') == 1
    _cleanup()


def test_set_null_unsets_key():
    # Setting a key to None (JSON null) unsets it at the top level.
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get(_SNAP, _KEY).get(_KEY) == 'hello'
    _snapd_conf.set(_SNAP, {_KEY: None})
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_all_keys():
    # get() with no keys returns all config as a dict.
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'value', _KEY2: 'value2'})
    config = _snapd_conf.get(_SNAP)
    assert isinstance(config, dict)
    assert config.get(_KEY) == 'value'
    assert config.get(_KEY2) == 'value2'
    _cleanup(_KEY2)


def test_get_specific_keys_returns_subset():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'alpha', _KEY2: 'beta'})
    subset = _snapd_conf.get(_SNAP, _KEY)
    assert _KEY in subset
    assert _KEY2 not in subset
    _cleanup(_KEY2)


def test_get_multiple_specific_keys():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'alpha', _KEY2: 'beta'})
    result = _snapd_conf.get(_SNAP, _KEY, _KEY2)
    assert result[_KEY] == 'alpha'
    assert result[_KEY2] == 'beta'
    _cleanup(_KEY2)


def test_get_option_not_found_raises():
    ensure_installed(_SNAP)
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, 'key-that-should-not-exist')
    assert ctx.value.kind == 'option-not-found'
    assert ctx.value.message


def test_get_option_not_found_value_contains_snap_and_key():
    ensure_installed(_SNAP)
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, 'key-that-should-not-exist')
    value = str(ctx.value.value)
    assert 'SnapName' in value
    assert 'Key' in value
    assert _SNAP in value
    assert 'key-that-should-not-exist' in value


def test_get_not_installed_snap_raises_option_not_found():
    # Config GET for a non-installed snap returns option-not-found (not snap-not-found).
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(_ABSENT_SNAP, 'any-key')
    assert ctx.value.kind == 'option-not-found'


# ---------------------------------------------------------------------------
# unset
# ---------------------------------------------------------------------------


def test_unset_key():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get(_SNAP, _KEY).get(_KEY) == 'hello'
    _snapd_conf.unset(_SNAP, _KEY)
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY)


def test_unset_nonexistent_key_no_error():
    # Unsetting a key that doesn't exist should not raise.
    ensure_installed(_SNAP)
    _snapd_conf.unset(_SNAP, 'key-that-does-not-exist')


def test_unset_multiple_keys():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'val1', _KEY2: 'val2'})
    _snapd_conf.unset(_SNAP, _KEY, _KEY2)
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY)
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY2)


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_set_not_installed_snap_raises_snap_not_found():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_conf.set(_ABSENT_SNAP, {'test-key': 'value'})
    assert ctx.value.kind == 'snap-not-found'


def test_unset_not_installed_snap_raises_snap_not_found():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_conf.unset(_ABSENT_SNAP, 'test-key')
    assert ctx.value.kind == 'snap-not-found'


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_set_multiple_keys_at_once():
    ensure_installed(_SNAP)
    values: dict[str, Any] = {_KEY: 'v1', _KEY2: 'v2'}
    _snapd_conf.set(_SNAP, values)
    result = _snapd_conf.get(_SNAP, _KEY, _KEY2)
    assert result[_KEY] == 'v1'
    assert result[_KEY2] == 'v2'
    _cleanup(_KEY2)


def test_set_empty_dict_no_error():
    # set({}) is a no-op — the API accepts an empty body without error.
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {})  # Should not raise.


def test_get_mixed_keys_raises_option_not_found():
    # When some requested keys exist and some don't, the API raises option-not-found
    # for the first missing key rather than returning partial results.
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'exists'})
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, _KEY, 'key-that-does-not-exist-xyz')
    assert ctx.value.kind == 'option-not-found'
    _cleanup()


def test_unset_dotted_path_no_error():
    # unset() accepts dotted-path keys and the API handles them without error.
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: {'nested': 'value'}})
    _snapd_conf.unset(_SNAP, f'{_KEY}.nested')  # Should not raise.
    _cleanup()


# ---------------------------------------------------------------------------
# configure hook failure -> ChangeError
# ---------------------------------------------------------------------------


def test_set_no_configure_hook_raises_change_error():
    # set/unset run the snap's configure hook as an async change. hello-world has no
    # configure hook, so snapd fails the change and we surface it as a ChangeError.
    ensure_installed('hello-world')
    with pytest.raises(_errors.ChangeError):
        _snapd_conf.set('hello-world', {'any-key': 'value'})


def test_unset_no_configure_hook_raises_change_error():
    ensure_installed('hello-world')
    with pytest.raises(_errors.ChangeError):
        _snapd_conf.unset('hello-world', 'any-key')
