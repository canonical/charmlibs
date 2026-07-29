#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_snaps: info, install, remove, refresh, hold, unhold.

Tests are ordered to minimise snap install/remove churn.  All tests that need
the snap *installed* run first, then all tests that need it *removed*, then
tests that inherently install/remove as part of the test logic.
"""

from __future__ import annotations

import datetime
import typing

import pytest

from charmlibs.snap import _client, _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed, list_channels, retry_on_rate_limit

# Snapd's own test snap, used for everything that needs real store semantics. Its two open
# channels on the latest track carry *different* revisions (stable is newer than edge), so a
# channel change is also a revision change -- which is what lets these tests tell 'tracking
# was updated' apart from 'the installed revision was updated'. latest/candidate and
# latest/beta are closed, so they are absent from the channel map and are not used here.
_SNAP = 'test-snapd-tools'
_CHANNEL = 'latest/stable'
_ALT_CHANNEL = 'latest/edge'

# The smallest classic-confined snap in the store, used wherever a test needs classic
# confinement rather than a particular snap. Published by snapd:
# https://github.com/canonical/snapd/tree/master/tests/lib/snaps
_CLASSIC_SNAP = 'test-snapd-classic-confinement'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# Test helper and possible future candidate for library public API.
# _list_snaps is an independent oracle (hits /v2/snaps) for the info()/missing-ok tests.
# list_channels (from conftest) sources store channel/revision info for install/refresh tests.
def _list_snaps() -> list[_snapd.Info]:
    """List all installed snaps."""
    info_dicts = _client.get('/v2/snaps')
    assert isinstance(info_dicts, list)
    info_dicts = typing.cast('list[dict[str, str]]', info_dicts)
    return [_snapd.Info._from_dict(info_dict) for info_dict in info_dicts]


# ---------------------------------------------------------------------------
# snap INSTALLED — tests that need the snap present
# ---------------------------------------------------------------------------


def test_info_installed():
    ensure_installed(_SNAP)
    info = _snapd.info(_SNAP)
    assert info.name == _SNAP
    assert info.tracking
    assert info.revision
    assert info.version
    # Independent oracle: /v2/snaps (list) should agree with /v2/snaps/{snap} (info).
    assert _SNAP in {s.name for s in _list_snaps()}


def test_info_fields():
    ensure_installed(_SNAP)
    info = _snapd.info(_SNAP)
    assert info.classic is False
    assert info.hold is None


def test_install_already_installed_returns_false():
    ensure_installed(_SNAP)
    result = _snapd.install(_SNAP)
    assert result is False


def test_refresh_no_updates_returns_false():
    ensure_installed(_SNAP, channel=_CHANNEL)
    result = retry_on_rate_limit(_snapd.refresh)(_SNAP, channel=_CHANNEL)
    assert result is False
    assert _snapd.info(_SNAP).tracking == _CHANNEL


def test_refresh_channel():
    # Refreshing to another channel moves both the tracking channel and the installed
    # revision, since the two channels hold different revisions. Asserting the revision as
    # well as the tracking is the point: a refresh that updated only the tracking would be
    # indistinguishable from a correct one if both channels held the same revision.
    ensure_installed(_SNAP, channel=_CHANNEL)
    channels = list_channels(_SNAP)
    assert channels[_CHANNEL].revision != channels[_ALT_CHANNEL].revision
    retry_on_rate_limit(_snapd.refresh)(_SNAP, channel=_ALT_CHANNEL)
    info = _snapd.info(_SNAP)
    assert info.tracking == _ALT_CHANNEL
    assert info.revision == channels[_ALT_CHANNEL].revision


def test_refresh_invalid_channel_raises():
    ensure_installed(_SNAP)
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.refresh)(_SNAP, channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'


def test_refresh_revision_not_available_raises():
    ensure_installed(_SNAP)
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.refresh)(_SNAP, revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


def test_hold_with_duration():
    ensure_installed(_SNAP)
    try:
        _snapd.hold(_SNAP, duration=datetime.timedelta(days=2))
        info = _snapd.info(_SNAP)
        assert info.hold is not None
        assert info.hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)
    finally:
        _snapd.unhold(_SNAP)


def test_hold_forever():
    ensure_installed(_SNAP)
    try:
        _snapd.hold(_SNAP)
        info = _snapd.info(_SNAP)
        # When held forever, snapd returns a far-future timestamp.
        assert info.hold is not None
    finally:
        _snapd.unhold(_SNAP)


def test_hold_already_held_no_error():
    # Holding an already-held snap is idempotent — no error is raised.
    ensure_installed(_SNAP)
    try:
        _snapd.hold(_SNAP)
        _snapd.hold(_SNAP)  # Second hold should not raise.
    finally:
        _snapd.unhold(_SNAP)


def test_unhold():
    ensure_installed(_SNAP)
    _snapd.hold(_SNAP)
    assert _snapd.info(_SNAP).hold is not None
    _snapd.unhold(_SNAP)
    assert _snapd.info(_SNAP).hold is None


def test_remove():
    # Last test in the "installed" block — leaves the snap removed for the next block.
    ensure_installed(_SNAP)
    _snapd.remove(_SNAP)
    with pytest.raises(_errors.NotFoundError):
        _snapd.info(_SNAP)


# ---------------------------------------------------------------------------
# snap REMOVED — tests that need the snap absent
# (after test_remove above, it is already gone)
# ---------------------------------------------------------------------------


def test_info_missing_raises():
    ensure_removed(_SNAP)
    # Independent oracle: the snap really is absent from /v2/snaps.
    assert _SNAP not in {s.name for s in _list_snaps()}
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd.info(_SNAP)
    assert ctx.value.kind == 'snap-not-found'


def test_remove_not_installed_returns_false():
    ensure_removed(_SNAP)
    result = _snapd.remove(_SNAP)
    assert result is False


def test_remove_purge_not_installed_returns_false():
    # purge=True on a non-installed snap behaves the same as purge=False: returns False.
    ensure_removed(_SNAP)
    result = _snapd.remove(_SNAP, purge=True)
    assert result is False


def test_refresh_not_installed_raises_base_snap_error():
    # The API returns an error with no 'kind' when refreshing a non-installed snap.
    # This is distinct from NotFoundError; it's a base Error.
    ensure_removed(_SNAP)
    with pytest.raises(_errors.Error) as ctx:
        retry_on_rate_limit(_snapd.refresh)(_SNAP)
    # No kind is set -- the message contains "is not installed" but snapd omits the kind field.
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_hold_not_installed_raises_snap_not_found_error():
    # hold() calls info() first, which raises NotFoundError with a proper kind.
    ensure_removed(_SNAP)
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd.hold(_SNAP)
    assert ctx.value.kind == 'snap-not-found'


def test_unhold_not_installed_no_error():
    # unhold on a non-installed snap succeeds silently (async Done).
    ensure_removed(_SNAP)
    _snapd.unhold(_SNAP)  # Should not raise.


def test_install_invalid_channel_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.install)(_SNAP, channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'
    assert 'channel' in ctx.value.message or 'no snap revision' in ctx.value.message


def test_install_revision_not_available_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.install)(_SNAP, revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


# ---------------------------------------------------------------------------
# INSTALL operations — tests that install as part of the test
# ---------------------------------------------------------------------------


def test_install():
    ensure_removed(_SNAP)
    retry_on_rate_limit(_snapd.install)(_SNAP)
    info = _snapd.info(_SNAP)
    assert info.name == _SNAP
    assert info.tracking == _CHANNEL
    # The installed revision should match the store's current latest/stable revision.
    assert info.revision == list_channels(_SNAP)[_CHANNEL].revision


def test_install_channel():
    ensure_removed(_SNAP)
    # Pre-flight: confirm the target channel actually exists in the store.
    channels = list_channels(_SNAP)
    assert _ALT_CHANNEL in channels
    retry_on_rate_limit(_snapd.install)(_SNAP, channel=_ALT_CHANNEL)
    info = _snapd.info(_SNAP)
    assert info.tracking == _ALT_CHANNEL
    # Installing a channel gets that channel's revision, not the default channel's.
    assert info.revision == channels[_ALT_CHANNEL].revision


def test_install_revision():
    # A revision on its own installs that exact revision, regardless of which channel it is
    # on. The revision is taken from the alternate channel rather than by subtracting one
    # from the default channel's: adjacent revision numbers need not exist in the store.
    ensure_removed(_SNAP)
    channels = list_channels(_SNAP)
    revision = channels[_ALT_CHANNEL].revision
    assert revision != channels[_CHANNEL].revision
    retry_on_rate_limit(_snapd.install)(_SNAP, revision=int(revision))
    info = _snapd.info(_SNAP)
    assert info.revision == revision


# ---------------------------------------------------------------------------
# classic confinement — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_install_needs_classic_raises():
    ensure_removed(_CLASSIC_SNAP)
    with pytest.raises(_errors.NeedsClassicError) as ctx:
        retry_on_rate_limit(_snapd.install)(_CLASSIC_SNAP)
    assert ctx.value.kind == 'snap-needs-classic'


def test_install_classic():
    ensure_removed(_CLASSIC_SNAP)
    retry_on_rate_limit(_snapd.install)(_CLASSIC_SNAP, classic=True)
    info = _snapd.info(_CLASSIC_SNAP)
    assert info.classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_install_nonexistent_snap_raises():
    with pytest.raises(_errors.NotFoundError) as ctx:
        retry_on_rate_limit(_snapd.install)(_ABSENT_SNAP)
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.value == _ABSENT_SNAP


def test_install_channel_and_revision():
    # Not mutually exclusive: snapd installs the revision and tracks the channel.
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    retry_on_rate_limit(_snapd.install)(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    info = _snapd.info(_SNAP)
    assert info.revision == edge
    assert info.tracking == _ALT_CHANNEL


def test_install_revision_not_on_channel_raises():
    # The store checks the revision against the channel, so asking for a revision that isn't
    # on the requested channel is an error -- reported against the channel, not the revision.
    ensure_removed(_SNAP)
    channels = list_channels(_SNAP)
    # A revision that really is in the store, on the alternate channel but not this one, so
    # the error is genuinely about the pairing rather than about an unknown revision.
    absent_from_channel = int(channels[_ALT_CHANNEL].revision)
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.install)(_SNAP, channel=_CHANNEL, revision=absent_from_channel)
    assert ctx.value.kind == 'snap-channel-not-available'


def test_refresh_channel_and_revision():
    ensure_installed(_SNAP, channel=_CHANNEL)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    retry_on_rate_limit(_snapd.refresh)(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    info = _snapd.info(_SNAP)
    assert info.revision == edge
    assert info.tracking == _ALT_CHANNEL


def test_refresh_revision_already_installed_still_refreshes():
    # Snapd runs a full refresh when a revision is specified, even if that revision is already
    # installed, so refresh reports that it did something. ensure() relies on knowing this.
    ensure_installed(_SNAP)
    current = _snapd.info(_SNAP).revision
    result = retry_on_rate_limit(_snapd.refresh)(_SNAP, revision=current)
    assert result is True
