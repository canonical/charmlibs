#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_aliases: alias, unalias."""

import subprocess

import pytest

from charmlibs.snap import _errors, _snapd_aliases
from conftest import ensure_installed

_SNAP = 'lxd'
_APP = 'lxc'
_ALIAS = 'test-functional-lxc-alias'


def _cleanup_alias() -> None:
    """Remove the test alias if it exists, ignoring errors."""
    try:
        _snapd_aliases.unalias(_ALIAS)
    except Exception:  # noqa: S110
        pass


def _alias_exists() -> bool:
    result = subprocess.check_output(['snap', 'aliases'], text=True)
    return any(
        line.split()[:3] == [f'{_SNAP}.{_APP}', _ALIAS, 'manual'] for line in result.splitlines()
    )


# ---------------------------------------------------------------------------
# alias
# ---------------------------------------------------------------------------


def test_alias_creates_alias():
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    assert _alias_exists()
    _cleanup_alias()


def test_alias_nonexistent_app_raises_snap_change_error():
    # Aliasing to an app that doesn't exist fails as an async change error.
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.SnapChangeError):
        _snapd_aliases.alias(_SNAP, 'nonexistent-app', _ALIAS)
    _cleanup_alias()


# ---------------------------------------------------------------------------
# unalias
# ---------------------------------------------------------------------------


def test_unalias_removes_alias():
    ensure_installed(_SNAP)
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    assert _alias_exists()
    _snapd_aliases.unalias(_ALIAS)
    assert not _alias_exists()


def test_unalias_nonexistent_alias_raises():
    # Unaliasing an alias that doesn't exist raises a base SnapError (no kind).
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.SnapError) as ctx:
        _snapd_aliases.unalias(_ALIAS)
    assert not ctx.value.kind
    assert 'cannot find' in ctx.value.message or _ALIAS in ctx.value.message


# ---------------------------------------------------------------------------
# _list_aliases
# ---------------------------------------------------------------------------


def test_list_aliases_returns_dict():
    ensure_installed(_SNAP)
    aliases = _snapd_aliases._list_aliases()
    assert isinstance(aliases, dict)


def test_list_aliases_includes_created_alias():
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    aliases = _snapd_aliases._list_aliases()
    assert _SNAP in aliases
    _cleanup_alias()
