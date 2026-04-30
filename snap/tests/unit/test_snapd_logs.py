# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime
import logging
import sys
from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_logs, SnapError, LogEntry
from charmlibs.snap._utils import _parse_timestamp
from conftest import result_of

if TYPE_CHECKING:
    from pytest import LogCaptureFixture

    from conftest import MockClient


class TestLogs:
    def test_logs_query_no_snaps(self, mock_client: MockClient):
        mock_client.get.return_value = []
        _snapd_logs.logs()
        mock_client.get.assert_called_once_with('/v2/logs', query={'n': 10})

    def test_logs_query_single_snap(self, mock_client: MockClient):
        mock_client.get.return_value = []
        _snapd_logs.logs('lxd')
        mock_client.get.assert_called_once_with('/v2/logs', query={'n': 10, 'names': 'lxd'})

    def test_logs_multiple_snaps(self, mock_client: MockClient):
        mock_client.get.return_value = []
        _snapd_logs.logs('lxd', 'vlc')
        query = mock_client.get.call_args.kwargs['query']
        assert query['names'] == 'lxd,vlc'

    def test_logs_custom_num_lines(self, mock_client: MockClient):
        mock_client.get.return_value = []
        _snapd_logs.logs('lxd', num_lines=50)
        query = mock_client.get.call_args.kwargs['query']
        assert query['n'] == 50

    def test_logs_parses_entries(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('logs_lxd.json')
        entries = _snapd_logs.logs('lxd')
        assert len(entries) == 10
        assert entries[0].sid == 'systemd'
        assert isinstance(entries[0].timestamp, datetime.datetime)

    def test_logs_pid_is_int(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('logs_lxd.json')
        entries = _snapd_logs.logs('lxd')
        assert entries[0].pid == 1
        assert isinstance(entries[0].pid, int)

    def test_logs_skips_malformed(self, mock_client: MockClient, caplog: LogCaptureFixture):
        mock_client.get.return_value = [
            {'timestamp': '2026-04-24T03:01:19.488008Z', 'sid': 'lxd', 'pid': '1'},
            # 'message' key missing
            {
                'timestamp': '2026-04-24T03:01:20.000000Z',
                'message': 'ok',
                'sid': 'lxd',
                'pid': '2',
            },
        ]
        with caplog.at_level(logging.WARNING, logger='charmlibs.snap._snapd_logs'):
            entries = _snapd_logs.logs('lxd')
        assert len(entries) == 1
        assert entries[0].pid == 2
        assert any('Skipping' in r.message for r in caplog.records)

    def test_logs_empty(self, mock_client: MockClient):
        mock_client.get.return_value = []
        assert _snapd_logs.logs('lxd') == []

    def test_logs_raises_snap_error(self, mock_client: MockClient):
        mock_client.get.side_effect = SnapError(
            'snap "hello-world" has no services',
            kind='app-not-found',
            value='',
            status_code=404,
            status='Not Found',
        )
        with pytest.raises(SnapError):
            _snapd_logs.logs('hello-world')

    def test_logs_returns_log_entry_objects(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('logs_lxd.json')
        entries = _snapd_logs.logs('lxd')
        assert all(isinstance(e, LogEntry) for e in entries)


class TestParseTimestamp:
    def test_z_suffix(self):
        ts = _parse_timestamp('2026-02-27T03:01:19.488008Z')
        assert ts.year == 2026
        assert ts.month == 2
        assert ts.day == 27
        assert ts.hour == 3

    def test_z_suffix_microseconds(self):
        ts = _parse_timestamp('2026-02-27T03:01:19.488008Z')
        assert ts.microsecond == 488008

    def test_z_suffix_utc(self):
        ts = _parse_timestamp('2026-02-27T03:01:19.488008Z')
        assert ts.tzinfo is not None
        assert ts.utcoffset() == datetime.timedelta(0)

    def test_z_suffix_high_precision(self):
        # 7-digit fraction should be truncated to 6 without error
        ts = _parse_timestamp('2026-02-27T03:01:19.4880089Z')
        assert ts.microsecond == 488008

    def test_z_suffix_short_fraction(self):
        # 5-digit fraction should be left-padded to 6 digits (0.13454 s = 134540 μs)
        ts = _parse_timestamp('2026-02-27T03:01:19.13454Z')
        assert ts.microsecond == 134540

    def test_z_suffix_four_digit_fraction(self):
        # 4-digit fraction: 0.0033 s = 3300 μs
        ts = _parse_timestamp('2026-02-27T03:01:19.0033Z')
        assert ts.microsecond == 3300

    @pytest.mark.skipif(
        sys.version_info < (3, 11),
        reason='fromisoformat does not support offset suffixes on Python 3.10',
    )
    def test_offset_suffix(self):
        ts = _parse_timestamp('2026-02-27T16:01:19.488008+13:00')
        assert ts.tzinfo is not None
        assert ts.utcoffset() == datetime.timedelta(hours=13)
        assert ts.hour == 16
