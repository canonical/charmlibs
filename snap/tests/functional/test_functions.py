#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _functions: ensure_installed and ensure_quota.

Tests are ordered to minimise snap install/remove churn.  All tests that need
the snap *installed* run first, then install-from-removed tests, then error
paths, with the classic-confinement tests grouped together.
"""

import pytest

from charmlibs import snap
from charmlibs.snap import _client, _errors, _functions
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import QUOTA_TEST_PREFIX as _QUOTA_PREFIX
from conftest import (
    ensure_installed_local,
    ensure_installed_store,
    ensure_removed,
    list_channels,
    reset_service_rate_limit,
)

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
# precondition for test_ensure_installed_same_revision_different_channel_switches_tracking below.
# It is used for that test alone; everything else here uses _SNAP.
_SHARED_REVISION_SNAP = 'hello-world'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# snap INSTALLED — no-op / refresh paths (snap stays present)
# ---------------------------------------------------------------------------


def test_ensure_installed_revision_no_op_if_same_revision():
    ensure_installed_store(_SNAP)
    current_revision = _snapd.list_one(_SNAP).revision
    result = _functions.ensure_installed(_SNAP, revision=int(current_revision))
    assert result is False


def test_ensure_installed_revision_no_op_if_same_revision_and_update_true():
    # update is ignored when a revision is specified: the revision fully determines which
    # revision to be on, so there's nothing to update to.
    ensure_installed_store(_SNAP)
    current_revision = _snapd.list_one(_SNAP).revision
    result = _functions.ensure_installed(_SNAP, revision=int(current_revision), update=True)
    assert result is False


def test_ensure_installed_revision_refreshes_on_different_revision():
    # The target revision is taken from the alternate channel rather than by subtracting one
    # from the installed revision: adjacent revision numbers need not exist in the store.
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    other_revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    assert _snapd.list_one(_SNAP).revision != other_revision
    did_something = _functions.ensure_installed(_SNAP, revision=int(other_revision))
    assert did_something is True
    assert _snapd.list_one(_SNAP).revision == other_revision


def test_ensure_installed_no_op_update_false():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel=_CHANNEL, update=False)
    assert result is False


def test_ensure_installed_no_op_normalized_channel():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel='latest', update=False)
    assert result is False


def test_ensure_installed_no_op_stable_normalized():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel='stable', update=False)
    assert result is False


def test_ensure_installed_refreshes_on_different_channel():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    did_something = _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL)
    assert did_something is True
    assert _snapd.list_one(_SNAP).tracking == _ALT_CHANNEL


def test_ensure_installed_no_updates_available_returns_false():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    # Already up-to-date — no updates available.
    result = _functions.ensure_installed(_SNAP, channel=_CHANNEL)
    assert result is False


# ---------------------------------------------------------------------------
# INSTALL — tests that install from a removed state
# ---------------------------------------------------------------------------


def test_ensure_installed_revision_installs_if_not_present():
    ensure_removed(_SNAP)
    revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    did_something = _functions.ensure_installed(_SNAP, revision=int(revision))
    assert did_something is True
    assert _snapd.list_one(_SNAP).revision == revision


def test_ensure_installed_revision_without_channel_tracks_latest_stable():
    # Installing by revision alone always tracks latest/stable, whichever channel the revision
    # was found on. Recorded here because it means the next refresh -- including an automatic
    # one -- moves the snap to latest/stable's revision.
    ensure_removed(_SNAP)
    revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    _functions.ensure_installed(_SNAP, revision=int(revision))
    info = _snapd.list_one(_SNAP)
    assert info.revision == revision
    # Tracks the default channel even though the revision came from the alternate one.
    assert info.tracking == _CHANNEL


def test_ensure_installed_channel_and_revision_installs_and_tracks_channel():
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    did_something = _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    assert did_something is True
    info = _snapd.list_one(_SNAP)
    assert info.revision == edge
    assert info.tracking == _ALT_CHANNEL


def test_ensure_installed_channel_and_revision_no_op_when_already_matching():
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    result = _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    assert result is False


def test_ensure_installed_same_revision_different_channel_switches_tracking():
    # When the revision is already installed but the snap tracks the wrong channel,
    # ensure_installed still refreshes -- snapd moves the tracking channel without changing
    # the revision.
    #
    # This needs one revision that is on two channels at once, so it cannot use _SNAP, whose
    # channels deliberately hold different revisions. hello-world is kept solely for this.
    snap_name = _SHARED_REVISION_SNAP
    channels = list_channels(snap_name)
    revision = channels['latest/edge'].revision
    if channels['latest/stable'].revision != revision:
        pytest.skip('latest/stable and latest/edge are on different revisions')
    ensure_removed(snap_name)
    _functions.ensure_installed(snap_name, channel=_ALT_CHANNEL, revision=revision)
    did_something = _functions.ensure_installed(snap_name, channel=_CHANNEL, revision=revision)
    assert did_something is True
    info = _snapd.list_one(snap_name)
    assert info.revision == revision
    assert info.tracking == _CHANNEL


def test_ensure_installed_installs_if_not_present():
    ensure_removed(_SNAP)
    did_something = _functions.ensure_installed(_SNAP)
    assert did_something is True
    assert _snapd.list_one(_SNAP).name == _SNAP


def test_ensure_installed_installs_at_default_channel():
    ensure_removed(_SNAP)
    _functions.ensure_installed(_SNAP)
    assert _snapd.list_one(_SNAP).tracking == _CHANNEL


def test_ensure_installed_installs_at_specified_channel():
    ensure_removed(_SNAP)
    _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL)
    assert _snapd.list_one(_SNAP).tracking == _ALT_CHANNEL


# ---------------------------------------------------------------------------
# error paths (snap removed)
# ---------------------------------------------------------------------------


def test_ensure_installed_bad_channel_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.APIError):
        _functions.ensure_installed(_SNAP, channel='not/a/real/channel')


def test_ensure_installed_revision_bad_revision_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.RevisionNotAvailableError):
        _functions.ensure_installed(_SNAP, revision=99999999)


def test_ensure_installed_revision_not_on_channel_raises():
    # The revision exists, but not on the requested channel: reported as a channel error.
    ensure_removed(_SNAP)
    absent_from_channel = int(list_channels(_SNAP)[_ALT_CHANNEL].revision)
    with pytest.raises(_errors.ChannelNotAvailableError):
        _functions.ensure_installed(_SNAP, channel=_CHANNEL, revision=absent_from_channel)


# ---------------------------------------------------------------------------
# classic confinement — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_ensure_installed_revision_installs_classic():
    ensure_removed(_CLASSIC_SNAP)
    channels = list_channels(_CLASSIC_SNAP)
    channel = 'latest/stable' if 'latest/stable' in channels else next(iter(channels))
    revision = channels[channel].revision
    _functions.ensure_installed(_CLASSIC_SNAP, channel=channel, revision=revision, classic=True)
    info = _snapd.list_one(_CLASSIC_SNAP)
    assert info.classic is True
    assert info.revision == revision


def test_ensure_installed_needs_classic_raises():
    ensure_removed(_CLASSIC_SNAP)
    with pytest.raises(_errors.NeedsClassicError):
        _functions.ensure_installed(_CLASSIC_SNAP)


def test_ensure_installed_installs_classic():
    ensure_removed(_CLASSIC_SNAP)
    _functions.ensure_installed(_CLASSIC_SNAP, classic=True)
    assert _snapd.list_one(_CLASSIC_SNAP).classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_ensure_installed_bad_snap_name_raises():
    # ensure_installed() finds the snap isn't installed and goes on to install it, so the
    # store is what reports the name as missing -- not the local check that got there first.
    with pytest.raises(_errors.NotInStoreError) as ctx:
        _functions.ensure_installed(_ABSENT_SNAP)
    assert type(ctx.value) is _errors.NotInStoreError


# ---------------------------------------------------------------------------
# ensure_installed with channel='' — treated as no channel (empty string is falsy)
# ---------------------------------------------------------------------------


def test_ensure_installed_empty_channel_installs_on_default_channel() -> None:
    ensure_removed(_SNAP)
    did_something = _functions.ensure_installed(_SNAP, channel='')
    assert did_something is True
    assert _snapd.list_one(_SNAP).tracking == _CHANNEL


def test_ensure_installed_empty_channel_refreshes_when_installed() -> None:
    # channel='' is falsy, so ensure_installed skips the channel-mismatch branch
    # and falls through to the update-check refresh (no-op here).
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel='')
    assert result is False


# ---------------------------------------------------------------------------
# ensure_quota
#
# Uses the locally-built snaps: test-snap (no services) and test-service-snap
# (one daemon). Group names carry QUOTA_TEST_PREFIX, and conftest's autouse
# fixture removes any that are left behind, sub-groups first.
# ---------------------------------------------------------------------------

_QUOTA_SNAP = 'test-snap'
_QUOTA_SERVICE_SNAP = 'test-service-snap'

_MiB = 1024**2


def test_ensure_quota_creates_group():
    ensure_installed_local(_QUOTA_SNAP)
    result = _functions.ensure_quota(
        f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB, cpu=(2, 50), threads=64
    )
    assert result
    info = snap.get_quota(f'{_QUOTA_PREFIX}one')
    assert info.snaps == [_QUOTA_SNAP]
    assert info.memory == 4 * _MiB
    assert info.cpu == (2, 50)
    assert info.threads == 64


def test_ensure_quota_no_change_returns_falsy():
    ensure_installed_local(_QUOTA_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB)
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', [_QUOTA_SNAP], memory=4 * _MiB)
    assert not result
    # A call that leaves out an argument leaves it alone, so it is still a no-op.
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', [_QUOTA_SNAP])
    assert not result


def test_ensure_quota_adds_snap_in_place():
    ensure_installed_local(_QUOTA_SNAP)
    ensure_installed_local(_QUOTA_SERVICE_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB)
    result = _functions.ensure_quota(
        f'{_QUOTA_PREFIX}one', [_QUOTA_SNAP, _QUOTA_SERVICE_SNAP], threads=64
    )
    assert result
    info = snap.get_quota(f'{_QUOTA_PREFIX}one')
    assert sorted(info.snaps) == sorted([_QUOTA_SNAP, _QUOTA_SERVICE_SNAP])
    assert info.memory == 4 * _MiB  # UNCHANGED, kept
    assert info.threads == 64  # added


def test_ensure_quota_removes_snap_by_recreating():
    ensure_installed_local(_QUOTA_SNAP)
    ensure_installed_local(_QUOTA_SERVICE_SNAP)
    _functions.ensure_quota(
        f'{_QUOTA_PREFIX}one', [_QUOTA_SNAP, _QUOTA_SERVICE_SNAP], memory=4 * _MiB
    )
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', [_QUOTA_SNAP])
    assert result
    info = snap.get_quota(f'{_QUOTA_PREFIX}one')
    assert info.snaps == [_QUOTA_SNAP]
    assert info.memory == 4 * _MiB  # UNCHANGED, carried over the re-creation


def test_ensure_quota_lowers_memory_by_recreating():
    ensure_installed_local(_QUOTA_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=8 * _MiB)
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', memory=4 * _MiB)
    assert result
    info = snap.get_quota(f'{_QUOTA_PREFIX}one')
    assert info.snaps == [_QUOTA_SNAP]  # UNCHANGED, carried over the re-creation
    assert info.memory == 4 * _MiB


def test_ensure_quota_none_removes_a_limit():
    ensure_installed_local(_QUOTA_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB, threads=64)
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', threads=None)
    assert result
    info = snap.get_quota(f'{_QUOTA_PREFIX}one')
    assert info.threads is None
    assert info.memory == 4 * _MiB


def test_ensure_quota_empty_snaps_empties_the_group():
    ensure_installed_local(_QUOTA_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB)
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', ())
    assert result
    info = snap.get_quota(f'{_QUOTA_PREFIX}one')
    assert info.snaps == []
    assert info.memory == 4 * _MiB


def test_ensure_quota_changes_cpu_in_place():
    ensure_installed_local(_QUOTA_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, cpu=(2, 50))
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', cpu=(None, 25))
    assert result
    assert snap.get_quota(f'{_QUOTA_PREFIX}one').cpu == (None, 25)


def test_ensure_quota_reinstalled_snap_is_put_back():
    # Removing a snap drops it from its group; calling ensure_quota again after a
    # reinstall adds it back -- the 'safe to call on every hook' pattern.
    ensure_installed_local(_QUOTA_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB)
    snap.remove(_QUOTA_SNAP)
    assert snap.get_quota(f'{_QUOTA_PREFIX}one').snaps == []
    ensure_installed_local(_QUOTA_SNAP)
    result = _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB)
    assert result
    assert snap.get_quota(f'{_QUOTA_PREFIX}one').snaps == [_QUOTA_SNAP]


def test_ensure_quota_services():
    ensure_installed_local(_QUOTA_SERVICE_SNAP)
    reset_service_rate_limit(_QUOTA_SERVICE_SNAP, 'daemon')  # joining a group restarts it
    _functions.ensure_quota(f'{_QUOTA_PREFIX}svc', _QUOTA_SERVICE_SNAP, memory=4 * _MiB)
    result = _functions.ensure_quota(
        f'{_QUOTA_PREFIX}svc-sub',
        services={_QUOTA_SERVICE_SNAP: ['daemon']},
        parent=f'{_QUOTA_PREFIX}svc',
        cpu=(None, 25),
    )
    assert result
    info = snap.get_quota(f'{_QUOTA_PREFIX}svc-sub')
    assert info.services == {_QUOTA_SERVICE_SNAP: ['daemon']}
    assert info.parent == f'{_QUOTA_PREFIX}svc'
    # Calling again with the same services is a no-op.
    result = _functions.ensure_quota(
        f'{_QUOTA_PREFIX}svc-sub',
        services={_QUOTA_SERVICE_SNAP: ['daemon']},
        parent=f'{_QUOTA_PREFIX}svc',
        cpu=(None, 25),
    )
    assert not result


def test_ensure_quota_recreate_restores_the_group_when_the_create_fails():
    # Dropping snap 1 and lowering the limit forces a re-create of A; the create then
    # fails because snap 2 is already in group B ('snap already in quota group').
    ensure_installed_local(_QUOTA_SNAP)
    ensure_installed_local(_QUOTA_SERVICE_SNAP)
    group_a = f'{_QUOTA_PREFIX}a'
    group_b = f'{_QUOTA_PREFIX}b'
    _functions.ensure_quota(group_a, _QUOTA_SNAP, memory=8 * _MiB)
    _functions.ensure_quota(group_b, _QUOTA_SERVICE_SNAP, memory=8 * _MiB)
    with pytest.raises(snap.APIError, match='already in quota group'):
        _functions.ensure_quota(group_a, [_QUOTA_SERVICE_SNAP], memory=4 * _MiB)
    # The previous group A was put back: snap 1 and the 8 MiB limit are as they were.
    info = snap.get_quota(group_a)
    assert info.snaps == [_QUOTA_SNAP]
    assert info.memory == 8 * _MiB
    info_b = snap.get_quota(group_b)
    assert info_b.snaps == [_QUOTA_SERVICE_SNAP]
    assert info_b.memory == 8 * _MiB


def test_ensure_quota_with_subgroups_cannot_recreate():
    ensure_installed_local(_QUOTA_SNAP)
    _functions.ensure_quota(f'{_QUOTA_PREFIX}parent', _QUOTA_SNAP, memory=8 * _MiB)
    _functions.ensure_quota(
        f'{_QUOTA_PREFIX}parent-sub', parent=f'{_QUOTA_PREFIX}parent', threads=64
    )
    # Lowering the parent's memory would re-create the group, which a group with
    # sub-groups cannot do: QuotaHasSubgroupsError, and nothing is changed.
    with pytest.raises(snap.QuotaHasSubgroupsError):
        _functions.ensure_quota(f'{_QUOTA_PREFIX}parent', memory=4 * _MiB)
    assert snap.get_quota(f'{_QUOTA_PREFIX}parent').memory == 8 * _MiB
    assert snap.get_quota(f'{_QUOTA_PREFIX}parent').subgroups == [f'{_QUOTA_PREFIX}parent-sub']


def test_ensure_quota_not_installed():
    ensure_removed(_QUOTA_SNAP)
    with pytest.raises(_errors.NotInstalledError):
        _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP, memory=4 * _MiB)
    with pytest.raises(snap.QuotaNotFoundError):
        snap.get_quota(f'{_QUOTA_PREFIX}one')


def test_ensure_quota_new_group_needs_a_limit():
    # A group cannot be created without a limit: a ValueError, before any request, rather
    # than snapd's APIError, so that it behaves like removing the only limit (below).
    ensure_installed_local(_QUOTA_SNAP)
    with pytest.raises(ValueError, match='at least one limit'):
        _functions.ensure_quota(f'{_QUOTA_PREFIX}one', _QUOTA_SNAP)
    with pytest.raises(snap.QuotaNotFoundError):
        snap.get_quota(f'{_QUOTA_PREFIX}one')


def test_ensure_quota_removing_the_last_limit_removes_the_group():
    # The natural charm call with the config option cleared: the snap should be
    # unconstrained, and a group cannot exist without a limit, so the group goes away --
    # and the call is then a no-op until a limit is given again.
    ensure_installed_local(_QUOTA_SNAP)
    group = f'{_QUOTA_PREFIX}one'
    _functions.ensure_quota(group, _QUOTA_SNAP, memory=4 * _MiB)
    assert _functions.ensure_quota(group, _QUOTA_SNAP, memory=None)
    with pytest.raises(snap.QuotaNotFoundError):
        snap.get_quota(group)
    assert not _functions.ensure_quota(group, _QUOTA_SNAP, memory=None)
    assert _functions.ensure_quota(group, _QUOTA_SNAP, memory=4 * _MiB)
    info = snap.get_quota(group)
    assert info.snaps == [_QUOTA_SNAP]
    assert info.memory == 4 * _MiB


def test_ensure_quota_cpu_without_cpu_set_is_stable():
    # snapd reports the unset cpu-set as an empty entry; cpu_set=None must not read that
    # as 'set' and re-create the group on every call.
    ensure_installed_local(_QUOTA_SNAP)
    group = f'{_QUOTA_PREFIX}one'
    assert _functions.ensure_quota(group, _QUOTA_SNAP, cpu=(None, 50), cpu_set=None)
    assert not _functions.ensure_quota(group, _QUOTA_SNAP, cpu=(None, 50), cpu_set=None)
    info = snap.get_quota(group)
    assert info.cpu == (None, 50)
    assert info.cpu_set is None


def test_ensure_quota_cpu_set_without_cpu_is_stable():
    # The mirror case: a group with only a CPU set is reported with an empty cpu entry.
    ensure_installed_local(_QUOTA_SNAP)
    group = f'{_QUOTA_PREFIX}one'
    assert _functions.ensure_quota(group, _QUOTA_SNAP, cpu=None, cpu_set=[0])
    assert not _functions.ensure_quota(group, _QUOTA_SNAP, cpu=None, cpu_set=[0])
    info = snap.get_quota(group)
    assert info.cpu is None
    assert info.cpu_set == [0]


def test_ensure_quota_cpu_none_recreates_once_and_keeps_the_cpu_set():
    # Removing the CPU limit re-creates the group (a limit can only be removed that way),
    # leaves the CPU set in place, and is stable afterwards.
    ensure_installed_local(_QUOTA_SNAP)
    group = f'{_QUOTA_PREFIX}one'
    _functions.ensure_quota(group, _QUOTA_SNAP, cpu=(1, 50), cpu_set=[0])
    assert _functions.ensure_quota(group, _QUOTA_SNAP, cpu=None)
    info = snap.get_quota(group)
    assert info.cpu is None
    assert info.cpu_set == [0]
    assert not _functions.ensure_quota(group, _QUOTA_SNAP, cpu=None)


def test_ensure_quota_removes_each_limit_in_turn():
    # Each limit can be removed while the others stay, and the result is stable.
    ensure_installed_local(_QUOTA_SNAP)
    group = f'{_QUOTA_PREFIX}one'
    _functions.ensure_quota(
        group, _QUOTA_SNAP, memory=8 * _MiB, cpu=(1, 50), cpu_set=[0], threads=128
    )

    assert _functions.ensure_quota(group, memory=None)
    info = snap.get_quota(group)
    assert info.memory is None
    assert (info.cpu, info.cpu_set, info.threads) == ((1, 50), [0], 128)
    assert not _functions.ensure_quota(group, memory=None)

    assert _functions.ensure_quota(group, cpu=None)
    info = snap.get_quota(group)
    assert info.cpu is None
    assert (info.cpu_set, info.threads) == ([0], 128)
    assert not _functions.ensure_quota(group, cpu=None)

    assert _functions.ensure_quota(group, cpu_set=None)
    info = snap.get_quota(group)
    assert info.cpu_set is None
    assert info.threads == 128
    assert not _functions.ensure_quota(group, cpu_set=None)

    # Removing the last remaining limit would remove the group itself, so threads goes
    # last, with a limit back in place first to keep the group around for the assertions.
    assert _functions.ensure_quota(group, memory=4 * _MiB)
    assert _functions.ensure_quota(group, threads=None)
    info = snap.get_quota(group)
    assert info.threads is None
    assert info.memory == 4 * _MiB
    assert not _functions.ensure_quota(group, threads=None)


def test_ensure_quota_recreate_preserves_a_journal_quota():
    # The reason ensure_quota copies the raw constraints: limits the library has no
    # argument for. A journal quota is set by posting directly, then the memory limit
    # is lowered, forcing a re-create that must carry the journal entry over.
    ensure_installed_local(_QUOTA_SNAP)  # no services: keeps restarts out of it
    group = f'{_QUOTA_PREFIX}journal'
    _client.post(
        '/v2/quotas',
        body={
            'action': 'ensure',
            'group-name': group,
            'snaps': [_QUOTA_SNAP],
            'constraints': {'memory': 8 * _MiB, 'journal': {'size': 16 * _MiB}},
        },
    )
    before = snap.get_quota(group)
    assert before._constraints['journal'] == {'size': 16 * _MiB}
    assert _functions.ensure_quota(group, memory=4 * _MiB)
    after = snap.get_quota(group)
    assert after._constraints['journal'] == before._constraints['journal']
    assert after.memory == 4 * _MiB
    # And the carried-over entry is not seen as a difference on the next call.
    assert not _functions.ensure_quota(group, memory=4 * _MiB)
