#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_snaps: list_one, install, remove, refresh, hold, unhold.

Tests are ordered to minimise snap install/remove churn.  All tests that need
hello-world *installed* run first, then all tests that need it *removed*, then
tests that inherently install/remove as part of the test logic.
"""

from __future__ import annotations

import datetime
from typing import cast

import pytest

from charmlibs.snap import _client, _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import _list, ensure_installed, ensure_removed, list_channels, retry_on_rate_limit

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# _list (from conftest) is an independent oracle (hits /v2/snaps) for the list_one and
# missing-ok tests. list_channels (also conftest) sources store channel/revision info for the
# install and refresh tests.


# ---------------------------------------------------------------------------
# hello-world INSTALLED — tests that need the snap present
# ---------------------------------------------------------------------------


def test_list_one_installed():
    ensure_installed('hello-world')
    info = _snapd.list_one('hello-world')
    assert info.name == 'hello-world'
    assert info.tracking
    assert info.revision
    assert info.version
    # Independent oracle: the /v2/snaps collection should agree with the /v2/snaps/{snap} that
    # list_one reads.
    assert 'hello-world' in {s.name for s in _list(None)}


def test_list_one_fields():
    ensure_installed('hello-world')
    info = _snapd.list_one('hello-world')
    assert info.classic is False
    assert info.hold is None


def test_install_already_installed_returns_false():
    ensure_installed('hello-world')
    result = _snapd.install('hello-world')
    assert result is False


def test_refresh_no_updates_returns_false():
    ensure_installed('hello-world', channel='latest/stable')
    result = retry_on_rate_limit(_snapd.refresh)('hello-world', channel='latest/stable')
    assert result is False
    assert _snapd.list_one('hello-world').tracking == 'latest/stable'


def test_refresh_channel():
    ensure_installed('hello-world', channel='latest/stable')
    # Pre-flight: confirm the target channel exists before refreshing to it.
    assert 'latest/candidate' in list_channels('hello-world')
    retry_on_rate_limit(_snapd.refresh)('hello-world', channel='latest/candidate')
    info = _snapd.list_one('hello-world')
    assert info.tracking == 'latest/candidate'


def test_refresh_invalid_channel_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.refresh)('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'


def test_refresh_revision_not_available_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.refresh)('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


def test_hold_with_duration():
    ensure_installed('hello-world')
    try:
        _snapd.hold('hello-world', duration=datetime.timedelta(days=2))
        info = _snapd.list_one('hello-world')
        assert info.hold is not None
        assert info.hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)
    finally:
        _snapd.unhold('hello-world')


def test_hold_forever():
    ensure_installed('hello-world')
    try:
        _snapd.hold('hello-world')
        info = _snapd.list_one('hello-world')
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
    assert _snapd.list_one('hello-world').hold is not None
    _snapd.unhold('hello-world')
    assert _snapd.list_one('hello-world').hold is None


def test_remove():
    # Last test in the "installed" block — leaves hello-world removed for the next block.
    ensure_installed('hello-world')
    _snapd.remove('hello-world')
    with pytest.raises(_errors.NotFoundError):
        _snapd.list_one('hello-world')


# ---------------------------------------------------------------------------
# hello-world REMOVED — tests that need the snap absent
# (after test_remove above, hello-world is already gone)
# ---------------------------------------------------------------------------


def test_list_one_missing_raises():
    ensure_removed('hello-world')
    # Independent oracle: the snap really is absent from /v2/snaps.
    assert 'hello-world' not in {s.name for s in _list(None)}
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd.list_one('hello-world')
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
        retry_on_rate_limit(_snapd.refresh)('hello-world')
    # No kind is set -- the message contains "is not installed" but snapd omits the kind field.
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_hold_not_installed_raises_snap_not_found_error():
    # hold() calls list_one() first, which raises NotFoundError with a proper kind.
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
        retry_on_rate_limit(_snapd.install)('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'
    assert 'channel' in ctx.value.message or 'no snap revision' in ctx.value.message


def test_install_revision_not_available_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.RevisionNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.install)('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


# ---------------------------------------------------------------------------
# hello-world INSTALL operations — tests that install as part of the test
# ---------------------------------------------------------------------------


def test_install():
    ensure_removed('hello-world')
    retry_on_rate_limit(_snapd.install)('hello-world')
    info = _snapd.list_one('hello-world')
    assert info.name == 'hello-world'
    assert info.tracking == 'latest/stable'
    # The installed revision should match the store's current latest/stable revision.
    assert info.revision == list_channels('hello-world')['latest/stable'].revision


def test_install_channel():
    ensure_removed('hello-world')
    # Pre-flight: confirm the target channel actually exists in the store.
    assert 'latest/candidate' in list_channels('hello-world')
    retry_on_rate_limit(_snapd.install)('hello-world', channel='latest/candidate')
    info = _snapd.list_one('hello-world')
    assert info.tracking == 'latest/candidate'


def test_install_revision():
    ensure_removed('hello-world')
    # hello-world revision 28 is one behind the current latest/stable revision (sourced
    # from the store rather than hard-coded, to document the relationship and catch drift).
    current = int(list_channels('hello-world')['latest/stable'].revision)
    previous = current - 1
    retry_on_rate_limit(_snapd.install)('hello-world', revision=previous)
    info = _snapd.list_one('hello-world')
    assert info.revision == str(previous)


# ---------------------------------------------------------------------------
# charmcraft (classic) — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_install_needs_classic_raises():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.NeedsClassicError) as ctx:
        retry_on_rate_limit(_snapd.install)('charmcraft')
    assert ctx.value.kind == 'snap-needs-classic'


def test_install_classic():
    ensure_removed('charmcraft')
    retry_on_rate_limit(_snapd.install)('charmcraft', classic=True)
    info = _snapd.list_one('charmcraft')
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
    ensure_removed('hello-world')
    edge = list_channels('hello-world')['latest/edge'].revision
    retry_on_rate_limit(_snapd.install)('hello-world', channel='latest/edge', revision=edge)
    info = _snapd.list_one('hello-world')
    assert info.revision == edge
    assert info.tracking == 'latest/edge'


def test_install_revision_not_on_channel_raises():
    # The store checks the revision against the channel, so asking for a revision that isn't
    # on the requested channel is an error -- reported against the channel, not the revision.
    ensure_removed('hello-world')
    channels = list_channels('hello-world')
    absent_from_stable = int(channels['latest/stable'].revision) - 1
    with pytest.raises(_errors.ChannelNotAvailableError) as ctx:
        retry_on_rate_limit(_snapd.install)(
            'hello-world', channel='latest/stable', revision=absent_from_stable
        )
    assert ctx.value.kind == 'snap-channel-not-available'


def test_refresh_channel_and_revision():
    ensure_installed('hello-world', channel='latest/stable')
    edge = list_channels('hello-world')['latest/edge'].revision
    retry_on_rate_limit(_snapd.refresh)('hello-world', channel='latest/edge', revision=edge)
    info = _snapd.list_one('hello-world')
    assert info.revision == edge
    assert info.tracking == 'latest/edge'


def test_refresh_revision_already_installed_still_refreshes():
    # Snapd runs a full refresh when a revision is specified, even if that revision is already
    # installed, so refresh reports that it did something. ensure() relies on knowing this.
    ensure_installed('hello-world')
    current = _snapd.list_one('hello-world').revision
    result = retry_on_rate_limit(_snapd.refresh)('hello-world', revision=current)
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
    ensure_removed('hello-world')
    current = str(list_channels('hello-world')['latest/stable'].revision)
    previous = str(int(current) - 1)
    retry_on_rate_limit(_snapd.install)('hello-world', revision=previous)
    retry_on_rate_limit(_snapd.refresh)('hello-world', revision=current)
    # The current revision is all that list_one and an unqualified list report.
    assert _snapd.list_one('hello-world').revision == current
    assert [i.revision for i in _list('hello-world')] == [current]
    # The replaced revision is still installed, and only all=True reveals it.
    assert sorted(i.revision for i in _list('hello-world', all=True)) == sorted([
        previous,
        current,
    ])


def test_list_several_snaps_in_one_request():
    ensure_installed('hello-world')
    ensure_installed('charmcraft', classic=True)
    listed = {i.name: i for i in _list(['hello-world', 'charmcraft'])}
    assert set(listed) == {'hello-world', 'charmcraft'}
    # The collection agrees with the per-snap endpoint list_one reads.
    for name, info in listed.items():
        assert info.revision == _snapd.list_one(name).revision


def test_list_bare_name_and_single_element_list_agree():
    ensure_installed('hello-world')
    assert [i.name for i in _list('hello-world')] == [i.name for i in _list(['hello-world'])]


def test_list_absent_snap_is_filtered_rather_than_an_error():
    # snapd filters instead of failing, so an absent name is simply missing from the result with
    # nothing to distinguish it from one that was never asked for. A plural API would have to
    # reconstruct the error client-side; list_one gets snapd's own, which is the shape we keep.
    ensure_installed('hello-world')
    assert [i.name for i in _list(['hello-world', _ABSENT_SNAP])] == ['hello-world']
    assert _list(_ABSENT_SNAP) == []
    with pytest.raises(_errors.NotFoundError):
        _snapd.list_one(_ABSENT_SNAP)


def test_list_no_names_lists_nothing_but_none_lists_everything():
    ensure_installed('hello-world')
    assert _list([]) == []
    assert _list(None) != []


def test_raw_api_empty_snaps_value_lists_everything():
    # The trap the helper avoids by making no request at all: snapd drops empty entries when it
    # parses 'snaps', so an empty value leaves the unfiltered query and answers with every
    # installed snap. Passing one through would turn a request for no snaps into a request for
    # all of them -- the same quirk the conf 'keys' and logs 'names' parameters have.
    #
    # Compared by name: snapd does not return these in a stable order.
    ensure_installed('hello-world')
    everything = {i.name for i in _list(None)}
    assert everything
    result = _client.get('/v2/snaps', query={'snaps': ''})
    assert isinstance(result, list)
    unfiltered = cast('list[dict[str, str]]', result)
    assert {s['name'] for s in unfiltered} == everything
