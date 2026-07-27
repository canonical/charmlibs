#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_logs: logs."""

import pytest

from charmlibs.snap import _client, _errors, _snapd_logs
from conftest import ensure_installed

_SNAP = 'kube-proxy'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# logs (kube-proxy installed)
# ---------------------------------------------------------------------------


def test_logs_returns_log_entries():
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, limit=5)
    assert isinstance(entries, list)


def test_logs_entries_have_expected_fields():
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, limit=5)
    for entry in entries:
        assert isinstance(entry, _snapd_logs.LogEntry)
        assert entry.timestamp
        assert isinstance(entry.message, str)
        assert isinstance(entry.sid, str)
        assert isinstance(entry.pid, int)


def test_logs_limit():
    # The limit parameter limits the number of results returned.
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, limit=3)
    assert len(entries) <= 3


def test_logs_limit_above_default():
    # The limit parameter is not capped at the snapd default of 10: requesting more
    # returns more (provided enough log entries are available).
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, limit=50)
    # kube-proxy is chatty enough to produce well over 10 entries shortly after install.
    assert len(entries) > 10


def test_logs_ordered_oldest_first():
    # Log entries are returned in chronological order: oldest first, newest last.
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, limit=50)
    timestamps = [entry.timestamp for entry in entries]
    assert timestamps == sorted(timestamps)


def test_logs_multiple_snaps():
    # Requesting logs for multiple snaps should not raise.
    ensure_installed(_SNAP, classic=True)
    ensure_installed('lxd')
    entries = _snapd_logs.logs(_SNAP, 'lxd', limit=10)
    assert isinstance(entries, list)


def test_logs_limit_zero_raises():
    # A non-positive limit is rejected client-side with a ValueError.
    with pytest.raises(ValueError, match='positive integer or None'):
        _snapd_logs.logs(_SNAP, limit=0)


def test_logs_limit_none_returns_all():
    # limit=None retrieves all available log entries (no limit).
    ensure_installed(_SNAP, classic=True)
    all_entries = _snapd_logs.logs(_SNAP, limit=None)
    limited = _snapd_logs.logs(_SNAP, limit=5)
    assert isinstance(all_entries, list)
    assert len(all_entries) >= len(limited)


def test_logs_no_snap_args():
    # Calling logs() with no snap arguments returns system-wide logs.
    entries = _snapd_logs.logs(limit=3)
    assert isinstance(entries, list)


# ---------------------------------------------------------------------------
# snap with no services (htop)
# ---------------------------------------------------------------------------


def test_logs_snap_with_no_services_raises():
    # A snap with no services raises AppNotFoundError.
    ensure_installed('htop')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_logs.logs('htop')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_logs_not_installed_snap_raises():
    # Requesting logs for an uninstalled snap raises NotFoundError.
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_logs.logs(_ABSENT_SNAP)
    assert ctx.value.kind == 'snap-not-found'


# ---------------------------------------------------------------------------
# empty entries in the 'names' query
#
# logs() rejects empty snap names client-side, so these go through _client to pin what snapd
# does with the query that rejection stops us from sending. It doesn't reject it: it splits
# 'names' on commas and drops the empty entries, so an empty name is not an error but a silent
# change to which logs you get -- which is the reason we don't pass one through.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('names', ['', ',', ',,'])
def test_empty_names_leave_no_filter(names: str):
    # Nothing is left once the empty entries are dropped, so there is nothing to filter on and
    # these queries return system-wide logs -- the same as omitting 'names' entirely. This is
    # what an empty name would do if we passed it through: widen a request for one snap's logs
    # into a request for every snap's logs, rather than fail.
    #
    # Entries are compared by their syslog identifiers, since new ones are logged all the time.
    # The unfiltered query runs first so that entries logged in between can only add identifiers
    # to the second result, which is why this is a superset rather than an equality.
    ensure_installed(_SNAP, classic=True)
    unfiltered = {entry['sid'] for entry in _client.get_logs(query={'n': -1})}
    assert unfiltered, 'no system-wide logs to compare against'
    result = {entry['sid'] for entry in _client.get_logs(query={'n': -1, 'names': names})}
    assert result.issuperset(unfiltered)


@pytest.mark.parametrize('names', [',htop', 'htop,', ',htop,'])
def test_empty_names_leave_the_named_snap(names: str):
    # The named snap is all that is left once the empty entries are dropped, so these queries
    # mean what naming it on its own means: snapd resolves the name and reports that it has no
    # services. An empty entry taken as a name of its own would report something else.
    ensure_installed('htop')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.get_logs(query={'n': -1, 'names': names})
    assert ctx.value.kind == 'app-not-found'
    assert ctx.value.message == 'snap "htop" has no services'
