#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_logs: logs."""

import pytest

from charmlibs.snap import _errors, _snapd_logs
from conftest import ensure_installed, ensure_removed

_SNAP = 'kube-proxy'


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


def test_logs_returns_log_entries():
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, num_lines=5)
    assert isinstance(entries, list)


def test_logs_entries_have_expected_fields():
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, num_lines=5)
    for entry in entries:
        assert isinstance(entry, _snapd_logs.LogEntry)
        assert entry.timestamp
        assert isinstance(entry.message, str)
        assert isinstance(entry.sid, str)
        assert isinstance(entry.pid, int)


def test_logs_num_lines():
    # The num_lines parameter limits the number of results returned.
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, num_lines=3)
    assert len(entries) <= 3


def test_logs_multiple_snaps():
    # Requesting logs for multiple snaps should not raise.
    ensure_installed(_SNAP, classic=True)
    ensure_installed('lxd')
    entries = _snapd_logs.logs(_SNAP, 'lxd', num_lines=10)
    assert isinstance(entries, list)


def test_logs_snap_with_no_services_raises():
    # A snap with no services raises SnapAppNotFoundError.
    ensure_installed('vlc')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_logs.logs('vlc')
    assert ctx.value.kind == 'app-not-found'


def test_logs_not_installed_snap_raises():
    # Requesting logs for an uninstalled snap raises SnapNotFoundError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd_logs.logs('hello-world')
    assert ctx.value.kind == 'snap-not-found'
