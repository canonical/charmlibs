#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_conf: get, set, unset."""

from __future__ import annotations

import typing
from typing import Any

import pytest

from charmlibs.snap import _errors, _snapd_conf
from conftest import ensure_installed, ensure_removed

_SNAP = 'lxd'
# A key prefix we use to avoid colliding with real lxd configuration.
_KEY = 'test-functional-key'
_KEY2 = 'test-functional-key2'


def _cleanup(*keys: str) -> None:
    """Unset test keys to avoid contaminating other tests."""
    _snapd_conf.unset(_SNAP, _KEY, *keys)


# ---------------------------------------------------------------------------
# set and get roundtrip
# ---------------------------------------------------------------------------


def test_set_and_get_bool_true():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: True})
    assert _snapd_conf.get(_SNAP, _KEY)[_KEY] is True
    _cleanup()


def test_set_and_get_bool_false():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: False})
    assert _snapd_conf.get(_SNAP, _KEY)[_KEY] is False
    _cleanup()


def test_set_and_get_integer():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 42})
    assert _snapd_conf.get(_SNAP, _KEY)[_KEY] == 42
    _cleanup()


def test_set_and_get_float():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 3.14})
    assert _snapd_conf.get(_SNAP, _KEY)[_KEY] == 3.14
    _cleanup()


def test_set_and_get_string():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get(_SNAP, _KEY)[_KEY] == 'hello'
    _cleanup()


def test_set_and_get_list():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: [1, 2, 3]})
    assert _snapd_conf.get(_SNAP, _KEY)[_KEY] == [1, 2, 3]
    _cleanup()


def test_set_and_get_dict():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: {'a': 1, 'b': 'two'}})
    assert _snapd_conf.get(_SNAP, _KEY)[_KEY] == {'a': 1, 'b': 'two'}
    _cleanup()


def test_set_null_unsets_key():
    # Setting a key to None (JSON null) unsets it at the top level.
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get(_SNAP, _KEY).get(_KEY) == 'hello'
    _snapd_conf.set(_SNAP, {_KEY: None})
    with pytest.raises(_errors.SnapOptionNotFoundError):
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
    with pytest.raises(_errors.SnapOptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, 'key-that-should-not-exist')
    assert ctx.value.kind == 'option-not-found'
    assert ctx.value.message


def test_get_option_not_found_value_contains_snap_and_key():
    ensure_installed(_SNAP)
    with pytest.raises(_errors.SnapOptionNotFoundError) as ctx:
        _snapd_conf.get(_SNAP, 'key-that-should-not-exist')
    exc = ctx.value
    di = typing.cast('dict[str, str]', exc.value)
    assert di['SnapName'] == _SNAP
    assert di['Key'] == 'key-that-should-not-exist'


def test_get_not_installed_snap_raises_option_not_found():
    # Config GET for a non-installed snap returns option-not-found (not snap-not-found).
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapOptionNotFoundError) as ctx:
        _snapd_conf.get('hello-world', 'any-key')
    assert ctx.value.kind == 'option-not-found'


# ---------------------------------------------------------------------------
# _get_one (private helper)
# ---------------------------------------------------------------------------


def test_get_one():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: {'nested': 'value'}})
    result = _snapd_conf._get_one(_SNAP, f'{_KEY}.nested')
    assert result == 'value'
    _cleanup()


def test_get_one_option_not_found_raises():
    ensure_installed(_SNAP)
    with pytest.raises(_errors.SnapOptionNotFoundError):
        _snapd_conf._get_one(_SNAP, 'nonexistent-key')


# ---------------------------------------------------------------------------
# unset
# ---------------------------------------------------------------------------


def test_unset_key():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'hello'})
    assert _snapd_conf.get(_SNAP, _KEY).get(_KEY) == 'hello'
    _snapd_conf.unset(_SNAP, _KEY)
    with pytest.raises(_errors.SnapOptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY)


def test_unset_nonexistent_key_no_error():
    # Unsetting a key that doesn't exist should not raise.
    ensure_installed(_SNAP)
    _snapd_conf.unset(_SNAP, 'key-that-does-not-exist')


def test_unset_multiple_keys():
    ensure_installed(_SNAP)
    _snapd_conf.set(_SNAP, {_KEY: 'val1', _KEY2: 'val2'})
    _snapd_conf.unset(_SNAP, _KEY, _KEY2)
    with pytest.raises(_errors.SnapOptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY)
    with pytest.raises(_errors.SnapOptionNotFoundError):
        _snapd_conf.get(_SNAP, _KEY2)


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_set_not_installed_snap_raises():
    # Config PUT on a non-installed snap raises SnapNotFoundError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd_conf.set('hello-world', {'any-key': 'value'})
    assert ctx.value.kind == 'snap-not-found'


def test_set_multiple_keys_at_once():
    ensure_installed(_SNAP)
    values: dict[str, Any] = {_KEY: 'v1', _KEY2: 'v2'}
    _snapd_conf.set(_SNAP, values)
    result = _snapd_conf.get(_SNAP, _KEY, _KEY2)
    assert result[_KEY] == 'v1'
    assert result[_KEY2] == 'v2'
    _cleanup(_KEY2)
