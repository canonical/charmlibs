#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_snaps: list_one, install, remove, refresh, hold, unhold.

Tests are ordered to minimise snap install/remove churn.  All tests that need
the snap *installed* run first, then all tests that need it *removed*, then
tests that inherently install/remove as part of the test logic.
"""

from __future__ import annotations

import datetime
from typing import cast

import pytest

from charmlibs.snap import _client, _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import (
    _list,
    ensure_installed_store,
    ensure_removed,
    list_channels,
    retry_on_rate_limit,
)

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


# _list (from conftest) is an independent oracle (hits /v2/snaps) for the list_one and
# missing-ok tests. list_channels (also conftest) sources store channel/revision info for the
# install and refresh tests.


# ---------------------------------------------------------------------------
# snap INSTALLED — tests that need the snap present
# ---------------------------------------------------------------------------


def test_list_one_installed():
    ensure_installed_store(_SNAP)
    info = _snapd.list_one(_SNAP)
    assert info.name == _SNAP
    assert info.tracking
    assert info.revision
    assert info.version
    # Independent oracle: the /v2/snaps collection should agree with the /v2/snaps/{snap}
    # that list_one reads.
    assert _SNAP in {s.name for s in _list(None)}


def test_list_one_fields():
    ensure_installed_store(_SNAP)
    info = _snapd.list_one(_SNAP)
    assert info.classic is False
    assert info.hold is None


def test_install_already_installed_returns_false():
    ensure_installed_store(_SNAP)
    result = _snapd.install(_SNAP)
    assert result is False


def test_refresh_no_updates_returns_false():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = retry_on_rate_limit(_snapd.refresh)(_SNAP, channel=_CHANNEL)
    assert result is False
    assert _snapd.list_one(_SNAP).tracking == _CHANNEL


def test_refresh_channel():
    # Refreshing to another channel moves both the tracking channel and the installed
    # revision, since the two channels hold different revisions. Asserting the revision as
    # well as the tracking is the point: a refresh that updated only the tracking would be
    # indistinguishable from a correct one if both channels held the same revision.
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    channels = list_channels(_SNAP)
    assert channels[_CHANNEL].revision != channels[_ALT_CHANNEL].revision
    retry_on_rate_limit(_snapd.refresh)(_SNAP, channel=_ALT_CHANNEL)
    info = _snapd.list_one(_SNAP)
    assert info.tracking == _ALT_CHANNEL
    assert info.revision == channels[_ALT_CHANNEL].revision


def test_refresh_invalid_channel_raises():
    ensure_installed_store(_SNAP)
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.refresh)(_SNAP, channel='garbage')
    assert ctx.value._kind == 'snap-channel-not-available'


def test_refresh_revision_not_available_raises():
    ensure_installed_store(_SNAP)
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.refresh)(_SNAP, revision=99999999)
    assert ctx.value._kind == 'snap-revision-not-available'


def test_hold_with_duration():
    ensure_installed_store(_SNAP)
    try:
        _snapd.hold(_SNAP, duration=datetime.timedelta(days=2))
        info = _snapd.list_one(_SNAP)
        assert info.hold is not None
        assert info.hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)
    finally:
        _snapd.unhold(_SNAP)


def test_hold_forever():
    ensure_installed_store(_SNAP)
    try:
        _snapd.hold(_SNAP)
        info = _snapd.list_one(_SNAP)
        # When held forever, snapd returns a far-future timestamp.
        assert info.hold is not None
    finally:
        _snapd.unhold(_SNAP)


def test_hold_already_held_no_error():
    # Holding an already-held snap is idempotent — no error is raised.
    ensure_installed_store(_SNAP)
    try:
        _snapd.hold(_SNAP)
        _snapd.hold(_SNAP)  # Second hold should not raise.
    finally:
        _snapd.unhold(_SNAP)


def test_unhold():
    ensure_installed_store(_SNAP)
    _snapd.hold(_SNAP)
    assert _snapd.list_one(_SNAP).hold is not None
    _snapd.unhold(_SNAP)
    assert _snapd.list_one(_SNAP).hold is None


def test_remove():
    # Last test in the "installed" block — leaves the snap removed for the next block.
    ensure_installed_store(_SNAP)
    _snapd.remove(_SNAP)
    with pytest.raises(_errors.NotInstalledError):
        _snapd.list_one(_SNAP)


# ---------------------------------------------------------------------------
# snap REMOVED — tests that need the snap absent
# (after test_remove above, it is already gone)
# ---------------------------------------------------------------------------


def test_list_one_missing_raises():
    ensure_removed(_SNAP)
    # Independent oracle: the snap really is absent from /v2/snaps.
    assert _SNAP not in {s.name for s in _list(None)}
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd.list_one(_SNAP)
    assert ctx.value._kind == 'snap-not-found'


def test_remove_not_installed_returns_false():
    ensure_removed(_SNAP)
    result = _snapd.remove(_SNAP)
    assert result is False


def test_remove_purge_not_installed_returns_false():
    # purge=True on a non-installed snap behaves the same as purge=False: returns False.
    ensure_removed(_SNAP)
    result = _snapd.remove(_SNAP, purge=True)
    assert result is False


def test_refresh_not_installed_raises_not_found():
    # A refresh needs the snap installed and still offered by the store, so it's the one
    # operation where both senses are reachable. snapd's answer here carries no kind at all, so
    # refresh() probes /v2/snaps/{snap}: absent means the local sense.
    ensure_removed(_SNAP)
    with pytest.raises(_errors.NotInstalledError) as ctx:
        retry_on_rate_limit(_snapd.refresh)(_SNAP)
    assert type(ctx.value) is _errors.NotInstalledError
    assert ctx.value._kind == 'snap-not-found'


def test_raw_refresh_not_installed_has_no_kind():
    # What the probe above exists to fix: snapd's own answer carries no 'kind' at all, so the
    # response alone can't be classified. The message says so, but only in prose.
    ensure_removed(_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _client.post(f'/v2/snaps/{_SNAP}', body={'action': 'refresh'})
    assert not ctx.value._kind
    assert 'not installed' in ctx.value.message


def test_hold_not_installed_raises_not_found():
    # hold() has the same kindless response to deal with, and solves it the same way.
    ensure_removed(_SNAP)
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd.hold(_SNAP)
    assert ctx.value._kind == 'snap-not-found'


def test_raw_hold_not_installed_has_no_kind():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _client.post(
            f'/v2/snaps/{_SNAP}',
            body={'action': 'hold', 'hold-level': 'general', 'time': 'forever'},
        )
    assert not ctx.value._kind
    assert 'not installed' in ctx.value.message


def test_unhold_not_installed_no_error():
    # unhold on a non-installed snap succeeds silently (async Done), matching the CLI: `snap
    # refresh --unhold <absent>` exits 0. A hold doesn't survive removal (see test_hold_does_not
    # _survive_removal), so there is never a hold left behind for this to have missed.
    ensure_removed(_SNAP)
    _snapd.unhold(_SNAP)  # Should not raise.


def test_hold_does_not_survive_removal():
    # Why unhold treats an absent snap as nothing to do rather than an error: removing a snap
    # takes its hold with it, so an absent snap cannot be holding back a refresh.
    ensure_installed_store(_SNAP)
    _snapd.hold(_SNAP)
    assert _snapd.list_one(_SNAP).hold is not None
    _snapd.remove(_SNAP)
    ensure_installed_store(_SNAP)
    assert _snapd.list_one(_SNAP).hold is None
    ensure_removed(_SNAP)


def test_install_invalid_channel_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.install)(_SNAP, channel='garbage')
    assert ctx.value._kind == 'snap-channel-not-available'
    assert 'channel' in ctx.value.message or 'no snap revision' in ctx.value.message


def test_install_revision_not_available_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.install)(_SNAP, revision=99999999)
    assert ctx.value._kind == 'snap-revision-not-available'


# ---------------------------------------------------------------------------
# INSTALL operations — tests that install as part of the test
# ---------------------------------------------------------------------------


def test_install():
    ensure_removed(_SNAP)
    retry_on_rate_limit(_snapd.install)(_SNAP)
    info = _snapd.list_one(_SNAP)
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
    info = _snapd.list_one(_SNAP)
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
    info = _snapd.list_one(_SNAP)
    assert info.revision == revision


# ---------------------------------------------------------------------------
# classic confinement — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_install_needs_classic_raises():
    ensure_removed(_CLASSIC_SNAP)
    with pytest.raises(_errors.NeedsClassicError) as ctx:
        retry_on_rate_limit(_snapd.install)(_CLASSIC_SNAP)
    assert ctx.value._kind == 'snap-needs-classic'


def test_install_classic():
    ensure_removed(_CLASSIC_SNAP)
    retry_on_rate_limit(_snapd.install)(_CLASSIC_SNAP, classic=True)
    info = _snapd.list_one(_CLASSIC_SNAP)
    assert info.classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_install_nonexistent_snap_raises():
    # The other sense: an install can only fail this way because the store has nothing by that
    # name. snapd sends the same ambiguous kind it uses for an absent local snap, and the
    # message ('snap not found', with no snap name) is the only thing that differs -- which is
    # why install classifies by what it asked for rather than by reading the message.
    with pytest.raises(_errors.NotInStoreError) as ctx:
        retry_on_rate_limit(_snapd.install)(_ABSENT_SNAP)
    assert type(ctx.value) is _errors.NotInStoreError
    assert ctx.value.message == 'snap not found'
    assert ctx.value._kind == 'snap-not-found'
    assert ctx.value._value == _ABSENT_SNAP


def test_install_channel_and_revision():
    # Not mutually exclusive: snapd installs the revision and tracks the channel.
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    retry_on_rate_limit(_snapd.install)(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    info = _snapd.list_one(_SNAP)
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
    assert ctx.value._kind == 'snap-channel-not-available'


def test_refresh_channel_and_revision():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    retry_on_rate_limit(_snapd.refresh)(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    info = _snapd.list_one(_SNAP)
    assert info.revision == edge
    assert info.tracking == _ALT_CHANNEL


def test_refresh_revision_already_installed_still_refreshes():
    # Snapd runs a full refresh when a revision is specified, even if that revision is already
    # installed, so refresh reports that it did something. ensure_installed() relies on knowing
    # this.
    ensure_installed_store(_SNAP)
    current = _snapd.list_one(_SNAP).revision
    result = retry_on_rate_limit(_snapd.refresh)(_SNAP, revision=current)
    assert result is True


# ---------------------------------------------------------------------------
# /v2/snaps as a collection — what `snap list` does that the library doesn't
#
# list_one is per-snap and reports only the current revision. The endpoint can do more: name
# several snaps in one request, and (with select=all) report every revision installed. Both are
# exercised through the _list test helper rather than library API, and the tests below pin the
# snapd behaviour that keeps them out of it.
# ---------------------------------------------------------------------------


def test_refresh_retains_the_previous_revision():
    # A refresh doesn't discard the revision it replaced: snapd keeps it installed but inactive.
    # So `snap list --all` reports the snap twice and names are no longer unique -- which is why
    # `all` would change the shape of any plural result, and stays a test-only concern here.
    # The two revisions are the two channels', rather than a revision and that revision minus
    # one: adjacent revision numbers need not exist in the store.
    ensure_removed(_SNAP)
    channels = list_channels(_SNAP)
    previous = channels[_ALT_CHANNEL].revision
    current = channels[_CHANNEL].revision
    assert previous != current
    retry_on_rate_limit(_snapd.install)(_SNAP, revision=previous)
    retry_on_rate_limit(_snapd.refresh)(_SNAP, revision=current)
    # The current revision is all that list_one and an unqualified list report.
    assert _snapd.list_one(_SNAP).revision == current
    assert [i.revision for i in _list(_SNAP)] == [current]
    # The replaced revision is still installed, and only all=True reveals it.
    assert sorted(i.revision for i in _list(_SNAP, all=True)) == sorted([previous, current])


def test_list_several_snaps_in_one_request():
    ensure_installed_store(_SNAP)
    ensure_installed_store(_CLASSIC_SNAP, classic=True)
    listed = {i.name: i for i in _list([_SNAP, _CLASSIC_SNAP])}
    assert set(listed) == {_SNAP, _CLASSIC_SNAP}
    # The collection agrees with the per-snap endpoint list_one reads.
    for name, info in listed.items():
        assert info.revision == _snapd.list_one(name).revision


def test_list_bare_name_and_single_element_list_agree():
    ensure_installed_store(_SNAP)
    assert [i.name for i in _list(_SNAP)] == [i.name for i in _list([_SNAP])]


def test_list_absent_snap_is_filtered_rather_than_an_error():
    # snapd filters instead of failing, so an absent name is simply missing from the result with
    # nothing to distinguish it from one that was never asked for. A plural API would have to
    # reconstruct the error client-side; list_one gets snapd's own, which is the shape we keep.
    ensure_installed_store(_SNAP)
    assert [i.name for i in _list([_SNAP, _ABSENT_SNAP])] == [_SNAP]
    assert _list(_ABSENT_SNAP) == []
    with pytest.raises(_errors.NotInstalledError):
        _snapd.list_one(_ABSENT_SNAP)


def test_list_no_names_lists_nothing_but_none_lists_everything():
    ensure_installed_store(_SNAP)
    assert _list([]) == []
    assert _list(None) != []


def test_raw_api_empty_snaps_value_lists_everything():
    # The trap the helper avoids by making no request at all: snapd drops empty entries when it
    # parses 'snaps', so an empty value leaves the unfiltered query and answers with every
    # installed snap. Passing one through would turn a request for no snaps into a request for
    # all of them -- the same quirk the conf 'keys' and logs 'names' parameters have.
    #
    # Compared by name: snapd does not return these in a stable order.
    ensure_installed_store(_SNAP)
    everything = {i.name for i in _list(None)}
    assert everything
    result = _client.get('/v2/snaps', query={'snaps': ''})
    assert isinstance(result, list)
    unfiltered = cast('list[dict[str, str]]', result)
    assert {s['name'] for s in unfiltered} == everything
