#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for the timestamp format snapd actually sends.

_utils.parse_timestamp normalizes a timestamp before handing it to datetime.fromisoformat,
rather than passing it as-is, because fromisoformat on Python 3.10 -- the version charms on
Ubuntu 22.04 run -- rejects the 'Z' suffix and any fractional part that isn't exactly 3 or 6
digits long. These tests pin what the live snapd on each Ubuntu base really emits, so that the
3.10 parser is matched against reality rather than against what the format is assumed to be.

The formats seen here are copied into the unit tests, which assert the exact datetime each one
parses to on every supported Python. Those run everywhere; these run against one snapd and one
Python per base.
"""

from __future__ import annotations

import datetime
import re
import typing
from typing import Any

from charmlibs.snap import _client, _snapd_logs, _utils
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed_local

# Locally-built snaps (tests/functional/snaps), so that nothing here depends on the store.
_SNAP = 'test-snap'
# The service snap emits a burst of log lines on startup, giving /v2/logs something to report.
_SERVICE_SNAP = 'test-service-snap'

# Snapd marshals a Go time.Time, which encoding/json writes with the RFC3339Nano layout
# "2006-01-02T15:04:05.999999999Z07:00". The 9s mean trailing zeros are trimmed from the
# fractional seconds, all the way to no fraction at all for a whole second; the Z07:00 means
# 'Z' when the time is UTC and an offset such as '+13:00' when it isn't.
_RFC3339_NANO = re.compile(
    r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'  # Date and time, always written in full.
    r'(?:\.\d{1,9})?'  # Fractional seconds, if any survived the trimming.
    r'(?:Z|[+-]\d{2}:\d{2})'  # Timezone: 'Z' for UTC, otherwise an offset.
)


def _raw_snap_info(name: str) -> dict[str, Any]:
    """The unparsed /v2/snaps/{name} result, which InstalledInfo is built from."""
    result = _client.get(f'/v2/snaps/{name}')
    assert isinstance(result, dict)
    return typing.cast('dict[str, Any]', result)


def _assert_parses(timestamp: str) -> datetime.datetime:
    """Assert the timestamp is a format we support, and return what we parse it as."""
    assert _RFC3339_NANO.fullmatch(timestamp), f'unexpected timestamp format: {timestamp!r}'
    parsed = _utils.parse_timestamp(timestamp)
    # Snapd always sends a timezone, in either of its two forms, so nothing here is naive.
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    # The 3.10 parser is checked against the live timestamp on every base, not only on the base
    # whose Python uses it. On 3.11+ parse_timestamp is fromisoformat, so this compares the
    # parser with the stdlib on a timestamp snapd really sent.
    fallback = _utils._parse_timestamp_310(timestamp)
    assert fallback == parsed
    assert fallback.utcoffset() == parsed.utcoffset()
    return parsed


def test_install_date_format():
    # install-date is the field most likely to land on a whole second, and so to arrive with no
    # fractional part at all -- the case the previous hand-rolled 3.10 parser raised ValueError
    # on. The library doesn't expose it, but it comes from the same endpoint as hold.
    ensure_installed_local(_SNAP)
    install_date = _raw_snap_info(_SNAP)['install-date']
    parsed = _assert_parses(install_date)
    assert parsed < datetime.datetime.now(tz=datetime.timezone.utc)


def test_hold_format():
    ensure_installed_local(_SNAP)
    try:
        _snapd.hold(_SNAP)
        raw_hold = _raw_snap_info(_SNAP)['hold']
        parsed = _assert_parses(raw_hold)
        # What InstalledInfo reports has been through the same parsing.
        info = _snapd.list_one(_SNAP)
        assert info.hold == parsed
    finally:
        _snapd.unhold(_SNAP)


def test_hold_forever_is_a_far_future_timestamp():
    # An indefinite hold has no distinct representation in snapd: it holds for Go's maximum
    # duration, 2**63-1 nanoseconds, which is a little over 292 years. InstalledInfo.hold
    # documents that, and a charm can only tell an indefinite hold from a definite one by the
    # date being absurd, so pin the arithmetic rather than just 'is not None'.
    ensure_installed_local(_SNAP)
    try:
        _snapd.hold(_SNAP)
        hold = _snapd.list_one(_SNAP).hold
        assert hold is not None
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        assert datetime.timedelta(days=290 * 365) < hold - now < datetime.timedelta(days=293 * 365)
    finally:
        _snapd.unhold(_SNAP)


def test_hold_with_duration_format():
    # A hold snapd computes from a duration we sent, rather than one it made up itself.
    ensure_installed_local(_SNAP)
    try:
        _snapd.hold(_SNAP, duration=datetime.timedelta(days=2))
        parsed = _assert_parses(_raw_snap_info(_SNAP)['hold'])
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        assert datetime.timedelta(days=1) < parsed - now < datetime.timedelta(days=3)
    finally:
        _snapd.unhold(_SNAP)


def test_log_timestamp_format():
    # /v2/logs timestamps come from journald rather than from snapd's own clock, so they're a
    # separate format risk: snapd converts them with .UTC(), and journald records microseconds.
    ensure_installed_local(_SERVICE_SNAP)
    result = _client.get_logs(query={'n': 5})
    entries = typing.cast('list[dict[str, Any]]', result)
    assert entries
    for entry in entries:
        parsed = _assert_parses(entry['timestamp'])
        assert parsed < datetime.datetime.now(tz=datetime.timezone.utc)
    # What LogEntry reports has been through the same parsing.
    log_entries = _snapd_logs.logs(_SERVICE_SNAP, limit=5)
    for log_entry in log_entries:
        assert log_entry.timestamp.tzinfo is not None


def test_timezone_is_read_from_the_timestamp():
    # Which of the two timezone forms a charm sees is decided by the timezone of the machine
    # snapd runs on, not by the Ubuntu base or the snapd version: a UTC machine (a CI runner, a
    # container) reports 'Z', and a machine on a local timezone reports an offset. Whichever
    # this machine produced, the offset we parse has to be the one the string carries -- the
    # 3.10 parser this replaced silently read every offset as UTC, putting hold and log
    # timestamps out by the machine's offset.
    ensure_installed_local(_SNAP)
    install_date = _raw_snap_info(_SNAP)['install-date']
    offset = _utils.parse_timestamp(install_date).utcoffset()
    if install_date.endswith('Z'):
        assert offset == datetime.timedelta(0)
    else:
        sign, hours, minutes = install_date[-6], install_date[-5:-3], install_date[-2:]
        assert sign in '+-'
        expected = datetime.timedelta(hours=int(hours), minutes=int(minutes))
        assert offset == (-expected if sign == '-' else expected)
