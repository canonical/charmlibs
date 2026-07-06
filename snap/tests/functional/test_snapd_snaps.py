#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_snaps: info, install, remove, refresh, hold, unhold.

Tests are ordered to minimise snap install/remove churn.  All tests that need
hello-world *installed* run first, then all tests that need it *removed*, then
tests that inherently install/remove as part of the test logic.
"""

from __future__ import annotations

import datetime
import typing
from typing import Any

import pytest

from charmlibs.snap import _client, _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# Test helpers and possible future candidates for library public API.
# _list_channels sources store channel/revision info for the install/refresh tests;
# _list_snaps is an independent oracle (hits /v2/snaps) for the info()/missing-ok tests.
def _list_snaps() -> list[_snapd.Info]:
    """List all installed snaps."""
    info_dicts = _client.get('/v2/snaps')
    assert isinstance(info_dicts, list)
    info_dicts = typing.cast('list[dict[str, str]]', info_dicts)
    return [_snapd.Info._from_dict(info_dict) for info_dict in info_dicts]


def _list_channels(snap: str) -> dict[str, _snapd.Info]:
    """List information about all channels of a snap available in the store."""
    results = _client.get('/v2/find', query={'name': snap})
    assert isinstance(results, list)
    results = typing.cast('list[dict[str, Any]]', results)
    # API returns a list of results, or an error if there are no matches.
    # We'll have one result for an exact name match.
    result, *_ = results
    channels = result['channels']
    return {
        k: _snapd.Info._from_dict({'name': snap, 'channel': k, **v}) for k, v in channels.items()
    }


# ---------------------------------------------------------------------------
# hello-world INSTALLED — tests that need the snap present
# ---------------------------------------------------------------------------


def test_info_installed():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel
    assert info.revision
    assert info.version
    # Independent oracle: /v2/snaps (list) should agree with /v2/snaps/{snap} (info).
    assert 'hello-world' in {s.name for s in _list_snaps()}


def test_info_fields():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.classic is False
    assert info.hold is None


def test_install_already_installed_returns_false():
    ensure_installed('hello-world')
    result = _snapd.install('hello-world')
    assert result is False


def test_refresh_no_updates_returns_false():
    ensure_installed('hello-world', channel='latest/stable')
    result = _snapd.refresh('hello-world', channel='latest/stable')
    assert result is False
    assert _snapd.info('hello-world').channel == 'latest/stable'


def test_refresh_channel():
    ensure_installed('hello-world', channel='latest/stable')
    # Pre-flight: confirm the target channel exists before refreshing to it.
    assert 'latest/candidate' in _list_channels('hello-world')
    _snapd.refresh('hello-world', channel='latest/candidate')
    info = _snapd.info('hello-world')
    assert info.channel == 'latest/candidate'


def test_refresh_invalid_channel_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        _snapd.refresh('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'


def test_refresh_revision_not_available_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        _snapd.refresh('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


def test_hold_with_duration():
    ensure_installed('hello-world')
    try:
        _snapd.hold('hello-world', duration=datetime.timedelta(days=2))
        info = _snapd.info('hello-world')
        assert info.hold is not None
        assert info.hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)
    finally:
        _snapd.unhold('hello-world')


def test_hold_forever():
    ensure_installed('hello-world')
    try:
        _snapd.hold('hello-world')
        info = _snapd.info('hello-world')
        # When held forever, snapd returns a far-future timestamp.
        assert info.hold is not None
    finally:
        _snapd.unhold('hello-world')


def test_hold_already_held_no_error():
    # Holding an already-held snap is idempotent — no error is raised.
    ensure_installed('hello-world')
    try:
        _snapd.hold('hello-world')
        _snapd.hold('hello-world')  # Second hold should not raise.
    finally:
        _snapd.unhold('hello-world')


def test_unhold():
    ensure_installed('hello-world')
    _snapd.hold('hello-world')
    assert _snapd.info('hello-world').hold is not None
    _snapd.unhold('hello-world')
    assert _snapd.info('hello-world').hold is None


def test_remove():
    # Last test in the "installed" block — leaves hello-world removed for the next block.
    ensure_installed('hello-world')
    _snapd.remove('hello-world')
    with pytest.raises(_errors.NotFoundError):
        _snapd.info('hello-world')


# ---------------------------------------------------------------------------
# hello-world REMOVED — tests that need the snap absent
# (after test_remove above, hello-world is already gone)
# ---------------------------------------------------------------------------


def test_info_missing_raises():
    ensure_removed('hello-world')
    # Independent oracle: the snap really is absent from /v2/snaps.
    assert 'hello-world' not in {s.name for s in _list_snaps()}
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd.info('hello-world')
    assert ctx.value.kind == 'snap-not-found'


def test_remove_not_installed_returns_false():
    ensure_removed('hello-world')
    result = _snapd.remove('hello-world')
    assert result is False


def test_remove_purge_not_installed_returns_false():
    # purge=True on a non-installed snap behaves the same as purge=False: returns False.
    ensure_removed('hello-world')
    result = _snapd.remove('hello-world', purge=True)
    assert result is False


def test_refresh_not_installed_raises_base_snap_error():
    # The API returns an error with no 'kind' when refreshing a non-installed snap.
    # This is distinct from NotFoundError; it's a base Error.
    ensure_removed('hello-world')
    with pytest.raises(_errors.Error) as ctx:
        _snapd.refresh('hello-world')
    # No kind is set -- the message contains "is not installed" but snapd omits the kind field.
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_hold_not_installed_raises_snap_not_found_error():
    # hold() calls info() first, which raises NotFoundError with a proper kind.
    ensure_removed('hello-world')
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd.hold('hello-world')
    assert ctx.value.kind == 'snap-not-found'


def test_unhold_not_installed_no_error():
    # unhold on a non-installed snap succeeds silently (async Done).
    ensure_removed('hello-world')
    _snapd.unhold('hello-world')  # Should not raise.


def test_install_invalid_channel_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        _snapd.install('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'
    assert 'channel' in ctx.value.message or 'no snap revision' in ctx.value.message


def test_install_revision_not_available_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        _snapd.install('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


# ---------------------------------------------------------------------------
# hello-world INSTALL operations — tests that install as part of the test
# ---------------------------------------------------------------------------


def test_install():
    ensure_removed('hello-world')
    _snapd.install('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel == 'latest/stable'
    # The installed revision should match the store's current latest/stable revision.
    assert info.revision == _list_channels('hello-world')['latest/stable'].revision


def test_install_channel():
    ensure_removed('hello-world')
    # Pre-flight: confirm the target channel actually exists in the store.
    assert 'latest/candidate' in _list_channels('hello-world')
    _snapd.install('hello-world', channel='latest/candidate')
    info = _snapd.info('hello-world')
    assert info.channel == 'latest/candidate'


def test_install_revision():
    ensure_removed('hello-world')
    # hello-world revision 28 is one behind the current latest/stable revision (sourced
    # from the store rather than hard-coded, to document the relationship and catch drift).
    current = int(_list_channels('hello-world')['latest/stable'].revision)
    previous = current - 1
    _snapd.install('hello-world', revision=previous)
    info = _snapd.info('hello-world')
    assert info.revision == str(previous)


# ---------------------------------------------------------------------------
# charmcraft (classic) — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_install_needs_classic_raises():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.NeedsClassicError) as ctx:
        _snapd.install('charmcraft')
    assert ctx.value.kind == 'snap-needs-classic'


def test_install_classic():
    ensure_removed('charmcraft')
    _snapd.install('charmcraft', classic=True)
    info = _snapd.info('charmcraft')
    assert info.classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_install_nonexistent_snap_raises():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd.install(_ABSENT_SNAP)
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.value == _ABSENT_SNAP


def test_install_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.install('hello-world', channel='latest/stable', revision=28)  # type: ignore[call-overload]


def test_refresh_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.refresh('hello-world', channel='latest/stable', revision=28)  # type: ignore[call-overload]
