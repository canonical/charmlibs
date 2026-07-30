#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_aliases: alias, unalias."""

from __future__ import annotations

import subprocess
import typing

import pytest

from charmlibs.snap import _client, _errors, _snapd_aliases
from conftest import ensure_installed, ensure_installed_local, ensure_removed

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

# A small Canonical-owned snap with several apps, so an alias can be reassigned between them.
# Defined in https://github.com/canonical/snapd/tree/master/tests/lib/snaps
_SNAP = 'test-snapd-tools'
_APP = 'echo'
_APP2 = 'cat'
_ALIAS = 'test-functional-alias'

# A second snap with a plain command, used only to claim _ALIAS first so that aliasing it to
# _SNAP conflicts. Locally built (tests/functional/snaps): the test needs two distinct snaps
# with an aliasable app, and nothing about the conflict depends on which snap the other is.
_OTHER_SNAP = 'test-alias-snap'
_OTHER_APP = 'hello'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# Test helper and possible future candidate for library public API.
def _list_aliases(snap: str) -> Mapping[str, Mapping[str, str]]:
    """List a snap's aliases, keyed by alias name: {alias: {command, status, ...}}."""
    aliases = _client.get('/v2/aliases')
    assert isinstance(aliases, dict)
    by_snap = typing.cast('dict[str, dict[str, dict[str, str]]]', aliases)
    return by_snap.get(snap, {})


def _cleanup_alias() -> None:
    """Remove the test alias if it exists, ignoring errors."""
    try:
        _snapd_aliases.unalias(_ALIAS)
    except Exception:  # noqa: S110
        pass


def _get_command_path(command: str) -> str:
    """Return the resolved PATH of a command, or '' if it isn't on PATH."""
    try:
        return subprocess.check_output(['which', command]).decode().strip()
    except subprocess.CalledProcessError:
        return ''


def _assert_alias_exists(app: str = _APP) -> None:
    """Assert the test alias points at `_SNAP.<app>`, via both the snapd API and PATH.

    An enabled alias is also a real command: snapd creates a `/snap/bin/<alias>` symlink that
    resolves on PATH. The snapd API view and the on-disk symlink are two views of the same fact,
    so we check both.
    """
    aliases = _list_aliases(_SNAP)
    assert _ALIAS in aliases
    assert aliases[_ALIAS].get('command') == f'{_SNAP}.{app}'
    assert _get_command_path(_ALIAS) == f'/snap/bin/{_ALIAS}'


# ---------------------------------------------------------------------------
# alias (snap installed)
# ---------------------------------------------------------------------------


def test_alias_creates_alias():
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    _assert_alias_exists()
    _cleanup_alias()


def test_alias_nonexistent_app_raises_snap_change_error():
    # Aliasing to an app that doesn't exist fails as an async change error.
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.ChangeError):
        _snapd_aliases.alias(_SNAP, 'nonexistent-app', _ALIAS)
    _cleanup_alias()


def test_alias_is_idempotent():
    # Calling alias() again with the same snap, app, and alias name succeeds silently.
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    _assert_alias_exists()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)  # Second call — no error.
    _assert_alias_exists()
    _cleanup_alias()


def test_alias_reassigns_within_same_snap():
    # Calling alias() with the same alias name but a different app of the same snap
    # silently reassigns the alias — no error raised.
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    _assert_alias_exists()
    _snapd_aliases.alias(_SNAP, _APP2, _ALIAS)  # Different app, same snap — no error.
    _assert_alias_exists(_APP2)
    _cleanup_alias()


def test_alias_name_conflicts_with_snap_command_namespace():
    # Using a snap's own name as the alias name conflicts with its command namespace.
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_aliases.alias(_SNAP, _APP, _SNAP)  # Alias name = snap name.
    assert 'conflicts with the command namespace' in ctx.value.message


# ---------------------------------------------------------------------------
# unalias (snap installed)
# ---------------------------------------------------------------------------


def test_unalias_removes_alias():
    ensure_installed(_SNAP)
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    _assert_alias_exists()
    _snapd_aliases.unalias(_ALIAS)
    # Removal drops the alias from both the snapd API listing and PATH.
    assert _ALIAS not in _list_aliases(_SNAP)
    assert not _get_command_path(_ALIAS)


def test_unalias_nonexistent_alias_raises():
    # Unaliasing an alias that doesn't exist raises a base Error (no kind).
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.Error) as ctx:
        _snapd_aliases.unalias(_ALIAS)
    assert not ctx.value.kind
    assert 'cannot find' in ctx.value.message or _ALIAS in ctx.value.message


# ---------------------------------------------------------------------------
# a second snap installed (test cross-snap alias conflicts)
# ---------------------------------------------------------------------------


def test_alias_duplicate_name_different_snap_raises():
    # An alias name already claimed by another snap raises ChangeError.
    ensure_installed(_SNAP)
    ensure_installed_local(_OTHER_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_aliases.alias(_OTHER_SNAP, _OTHER_APP, _ALIAS)
    assert 'already enabled for' in ctx.value.message
    _cleanup_alias()


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_alias_not_installed_snap_raises():
    # snapd answers with the 'snap-not-installed' kind here, rather than the 'snap-not-found' it
    # uses on most endpoints. That kind is unambiguous -- only remove and alias send it, and both
    # act on an installed snap -- so the client maps it straight to the subclass, and alias needs
    # no narrowing of its own to report the same type every other operation reports.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_aliases.alias(_ABSENT_SNAP, 'hello', 'test-not-installed-alias')
    assert type(ctx.value) is _errors.NotInstalledError
    assert ctx.value.kind == 'snap-not-installed'


# ---------------------------------------------------------------------------
# empty and blank fields
#
# The three fields go in a JSON body, so snapd sees each exactly as passed and reports an
# unusable one itself, naming it verbatim. alias() and unalias() still reject empty and blank
# values up front, for the same reason as the rest of the library: they are caller errors, and
# the app name is only reported once the change runs. These go through _client to pin what
# snapd would have said.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('value', ['', ' ', '\t'])
def test_alias_rejects_empty_and_blank_fields(value: str):
    ensure_installed(_SNAP)
    for args in ((value, _APP, _ALIAS), (_SNAP, value, _ALIAS), (_SNAP, _APP, value)):
        with pytest.raises(ValueError):
            _snapd_aliases.alias(*args)
    with pytest.raises(ValueError):
        _snapd_aliases.unalias(value)


@pytest.mark.parametrize('snap_name', ['', ' '])
def test_raw_alias_empty_or_blank_snap_is_not_installed(snap_name: str):
    # Neither is read as a snap that could exist, so both are reported the same way.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _client.post(
            '/v2/aliases',
            body={'action': 'alias', 'snap': snap_name, 'app': _APP, 'alias': _ALIAS},
        )
    assert ctx.value.kind == 'snap-not-installed'
    assert ctx.value.value == snap_name


@pytest.mark.parametrize('app', ['', ' '])
def test_raw_alias_empty_or_blank_app_fails_the_change(app: str):
    # The app name is not validated up front by snapd: the change is created and only fails once
    # the alias is set up, which is a round trip and a change for a value that can never work.
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.ChangeError) as ctx:
        _client.post(
            '/v2/aliases', body={'action': 'alias', 'snap': _SNAP, 'app': app, 'alias': _ALIAS}
        )
    assert f'target application "{app}" does not exist' in ctx.value.message


@pytest.mark.parametrize('alias_name', ['', ' '])
def test_raw_alias_empty_or_blank_alias_is_invalid(alias_name: str):
    ensure_installed(_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _client.post(
            '/v2/aliases',
            body={'action': 'alias', 'snap': _SNAP, 'app': _APP, 'alias': alias_name},
        )
    assert ctx.value.message == f'invalid alias name: "{alias_name}"'


@pytest.mark.parametrize('alias_name', ['', ' '])
def test_raw_unalias_empty_or_blank_alias_is_not_found(alias_name: str):
    with pytest.raises(_errors.APIError) as ctx:
        _client.post('/v2/aliases', body={'action': 'unalias', 'alias': alias_name})
    assert ctx.value.message == f'cannot find manual alias "{alias_name}" in any snap'


# ---------------------------------------------------------------------------
# unalias after snap removed — last because it removes the snap
# ---------------------------------------------------------------------------


def test_unalias_after_snap_removed_raises():
    # Aliases don't survive snap removal; unaliasing after removal raises the same error
    # as attempting to remove an alias that was never created.
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    ensure_removed(_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_aliases.unalias(_ALIAS)
    assert not ctx.value.kind
    assert 'cannot find' in ctx.value.message
