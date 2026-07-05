#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_logs: logs."""

import pytest

from charmlibs.snap import _errors, _snapd_logs
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
