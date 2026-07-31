#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _functions: ensure.

Tests are ordered to minimise snap install/remove churn.  All tests that need
the snap *installed* run first, then install-from-removed tests, then error
paths, with the classic-confinement tests grouped together.
"""

import pytest

from charmlibs.snap import _errors, _functions
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed, list_channels

# The smallest classic-confined snap in the store, used wherever a test needs classic
# confinement rather than a particular snap. Published by snapd:
# https://github.com/canonical/snapd/tree/master/tests/lib/snaps
_CLASSIC_SNAP = 'test-snapd-classic-confinement'

# Snapd's own test snap: its two open channels on the latest track hold different revisions,
# so switching channel also switches revision. latest/candidate and latest/beta are closed
# and absent from the channel map, so the alternate channel here is edge.
_SNAP = 'test-snapd-tools'
_CHANNEL = 'latest/stable'
_ALT_CHANNEL = 'latest/edge'

# hello-world is the one snap whose channels all carry the *same* revision, which is the
# precondition for test_ensure_same_revision_different_channel_switches_tracking below.
# It is used for that test alone; everything else here uses _SNAP.
_SHARED_REVISION_SNAP = 'hello-world'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# snap INSTALLED — no-op / refresh paths (snap stays present)
# ---------------------------------------------------------------------------


def test_ensure_revision_no_op_if_same_revision():
    ensure_installed(_SNAP)
    current_revision = _snapd.list_one(_SNAP).revision
    result = _functions.ensure(_SNAP, revision=int(current_revision))
    assert result is False


def test_ensure_revision_no_op_if_same_revision_and_update_true():
    # update is ignored when a revision is specified: the revision fully determines which
    # revision to be on, so there's nothing to update to.
    ensure_installed(_SNAP)
    current_revision = _snapd.list_one(_SNAP).revision
    result = _functions.ensure(_SNAP, revision=int(current_revision), update=True)
    assert result is False


def test_ensure_revision_refreshes_on_different_revision():
    # The target revision is taken from the alternate channel rather than by subtracting one
    # from the installed revision: adjacent revision numbers need not exist in the store.
    ensure_installed(_SNAP, channel=_CHANNEL)
    other_revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    assert _snapd.list_one(_SNAP).revision != other_revision
    did_something = _functions.ensure(_SNAP, revision=int(other_revision))
    assert did_something is True
    assert _snapd.list_one(_SNAP).revision == other_revision


def test_ensure_no_op_update_false():
    ensure_installed(_SNAP, channel=_CHANNEL)
    result = _functions.ensure(_SNAP, channel=_CHANNEL, update=False)
    assert result is False


def test_ensure_no_op_normalized_channel():
    ensure_installed(_SNAP, channel=_CHANNEL)
    result = _functions.ensure(_SNAP, channel='latest', update=False)
    assert result is False


def test_ensure_no_op_stable_normalized():
    ensure_installed(_SNAP, channel=_CHANNEL)
    result = _functions.ensure(_SNAP, channel='stable', update=False)
    assert result is False


def test_ensure_refreshes_on_different_channel():
    ensure_installed(_SNAP, channel=_CHANNEL)
    did_something = _functions.ensure(_SNAP, channel=_ALT_CHANNEL)
    assert did_something is True
    assert _snapd.list_one(_SNAP).tracking == _ALT_CHANNEL


def test_ensure_no_updates_available_returns_false():
    ensure_installed(_SNAP, channel=_CHANNEL)
    # Already up-to-date — no updates available.
    result = _functions.ensure(_SNAP, channel=_CHANNEL)
    assert result is False


# ---------------------------------------------------------------------------
# INSTALL — tests that install from a removed state
# ---------------------------------------------------------------------------


def test_ensure_revision_installs_if_not_present():
    ensure_removed(_SNAP)
    revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    did_something = _functions.ensure(_SNAP, revision=int(revision))
    assert did_something is True
    assert _snapd.list_one(_SNAP).revision == revision


def test_ensure_revision_without_channel_tracks_latest_stable():
    # Installing by revision alone always tracks latest/stable, whichever channel the revision
    # was found on. Recorded here because it means the next refresh -- including an automatic
    # one -- moves the snap to latest/stable's revision.
    ensure_removed(_SNAP)
    revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    _functions.ensure(_SNAP, revision=int(revision))
    info = _snapd.list_one(_SNAP)
    assert info.revision == revision
    # Tracks the default channel even though the revision came from the alternate one.
    assert info.tracking == _CHANNEL


def test_ensure_channel_and_revision_installs_and_tracks_channel():
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    did_something = _functions.ensure(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    assert did_something is True
    info = _snapd.list_one(_SNAP)
    assert info.revision == edge
    assert info.tracking == _ALT_CHANNEL


def test_ensure_channel_and_revision_no_op_when_already_matching():
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    _functions.ensure(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    result = _functions.ensure(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    assert result is False


def test_ensure_same_revision_different_channel_switches_tracking():
    # When the revision is already installed but the snap tracks the wrong channel, ensure
    # still refreshes -- snapd moves the tracking channel without changing the revision.
    #
    # This needs one revision that is on two channels at once, so it cannot use _SNAP, whose
    # channels deliberately hold different revisions. hello-world is kept solely for this.
    snap_name = _SHARED_REVISION_SNAP
    channels = list_channels(snap_name)
    revision = channels['latest/edge'].revision
    if channels['latest/stable'].revision != revision:
        pytest.skip('latest/stable and latest/edge are on different revisions')
    ensure_removed(snap_name)
    _functions.ensure(snap_name, channel=_ALT_CHANNEL, revision=revision)
    did_something = _functions.ensure(snap_name, channel=_CHANNEL, revision=revision)
    assert did_something is True
    info = _snapd.list_one(snap_name)
    assert info.revision == revision
    assert info.tracking == _CHANNEL


def test_ensure_installs_if_not_present():
    ensure_removed(_SNAP)
    did_something = _functions.ensure(_SNAP)
    assert did_something is True
    assert _snapd.list_one(_SNAP).name == _SNAP


def test_ensure_installs_at_default_channel():
    ensure_removed(_SNAP)
    _functions.ensure(_SNAP)
    assert _snapd.list_one(_SNAP).tracking == _CHANNEL


def test_ensure_installs_at_specified_channel():
    ensure_removed(_SNAP)
    _functions.ensure(_SNAP, channel=_ALT_CHANNEL)
    assert _snapd.list_one(_SNAP).tracking == _ALT_CHANNEL


# ---------------------------------------------------------------------------
# error paths (snap removed)
# ---------------------------------------------------------------------------


def test_ensure_bad_channel_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.APIError):
        _functions.ensure(_SNAP, channel='not/a/real/channel')


def test_ensure_revision_bad_revision_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.RevisionNotAvailableError):
        _functions.ensure(_SNAP, revision=99999999)


def test_ensure_revision_not_on_channel_raises():
    # The revision exists, but not on the requested channel: reported as a channel error.
    ensure_removed(_SNAP)
    absent_from_channel = int(list_channels(_SNAP)[_ALT_CHANNEL].revision)
    with pytest.raises(_errors.ChannelNotAvailableError):
        _functions.ensure(_SNAP, channel=_CHANNEL, revision=absent_from_channel)


# ---------------------------------------------------------------------------
# classic confinement — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_ensure_revision_installs_classic():
    ensure_removed(_CLASSIC_SNAP)
    channels = list_channels(_CLASSIC_SNAP)
    channel = 'latest/stable' if 'latest/stable' in channels else next(iter(channels))
    revision = channels[channel].revision
    _functions.ensure(_CLASSIC_SNAP, channel=channel, revision=revision, classic=True)
    info = _snapd.list_one(_CLASSIC_SNAP)
    assert info.classic is True
    assert info.revision == revision


def test_ensure_needs_classic_raises():
    ensure_removed(_CLASSIC_SNAP)
    with pytest.raises(_errors.NeedsClassicError):
        _functions.ensure(_CLASSIC_SNAP)


def test_ensure_installs_classic():
    ensure_removed(_CLASSIC_SNAP)
    _functions.ensure(_CLASSIC_SNAP, classic=True)
    assert _snapd.list_one(_CLASSIC_SNAP).classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_ensure_bad_snap_name_raises():
    # ensure() finds the snap isn't installed and goes on to install it, so the store is what
    # reports the name as missing -- not the local check that got there first.
    with pytest.raises(_errors.NotInStoreError) as ctx:
        _functions.ensure(_ABSENT_SNAP)
    assert type(ctx.value) is _errors.NotInStoreError


# ---------------------------------------------------------------------------
# ensure with channel='' — treated as no channel (empty string is falsy)
# ---------------------------------------------------------------------------


def test_ensure_empty_channel_installs_on_default_channel() -> None:
    ensure_removed(_SNAP)
    did_something = _functions.ensure(_SNAP, channel='')
    assert did_something is True
    assert _snapd.list_one(_SNAP).tracking == _CHANNEL


def test_ensure_empty_channel_refreshes_when_installed() -> None:
    # channel='' is falsy, so ensure skips the channel-mismatch branch
    # and falls through to the update-check refresh (no-op here).
    ensure_installed(_SNAP, channel=_CHANNEL)
    result = _functions.ensure(_SNAP, channel='')
    assert result is False
