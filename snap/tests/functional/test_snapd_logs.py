#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_logs: logs."""

from __future__ import annotations

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
# logs() rejects empty snap names client-side, so these tests go through _client to pin what
# snapd does with the query that rejection stops us from sending. That matters because the
# rejection is our own API choice, not a workaround for a snapd error: snapd accepts these
# queries, and what it does with them is the reason we don't pass them through.
# ---------------------------------------------------------------------------

# ','.join() of one, two, or three empty snap names.
_EMPTY_NAMES = ['', ',', ',,']


@pytest.mark.parametrize('names', _EMPTY_NAMES)
def test_empty_names_query_does_not_raise(names: str):
    # snapd splits 'names' on commas and drops the empty entries, so a query of nothing but
    # empty entries is not an error: it returns log entries like any other query.
    ensure_installed(_SNAP, classic=True)
    result = _client.get_logs(query={'n': 5, 'names': names})
    assert isinstance(result, list)


@pytest.mark.parametrize('names', _EMPTY_NAMES)
def test_empty_names_query_is_not_a_filter(names: str):
    # Once the empty entries are dropped there is nothing left to filter on, so these queries
    # return system-wide logs -- the same as omitting 'names' entirely. This is why logs('')
    # is rejected client-side: an empty name silently widens the query to every snap's logs
    # instead of failing, which is the opposite of what a caller passing a name is asking for.
    #
    # Compared against a single-snap query rather than an omitted 'names', so that the two
    # results differ by more than timing. The filtered query runs first, so entries logged in
    # between can only add to the unfiltered result -- they can never break the comparison.
    ensure_installed(_SNAP, classic=True)
    ensure_installed('lxd')  # A second snap with services, so filtering is observable.
    filtered = {entry['sid'] for entry in _client.get_logs(query={'n': -1, 'names': _SNAP})}
    unfiltered = {entry['sid'] for entry in _client.get_logs(query={'n': -1, 'names': names})}
    assert unfiltered > filtered
