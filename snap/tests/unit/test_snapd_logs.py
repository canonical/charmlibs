# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime
import logging
import sys
from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import LogEntry, _snapd_logs
from charmlibs.snap._utils import parse_timestamp
from conftest import result_of

if TYPE_CHECKING:
    from pytest import LogCaptureFixture

    from conftest import MockClient


class TestLogs:
    def test_logs_query_no_snaps(self, mock_client: MockClient):
        mock_client.get_logs.return_value = []
        _snapd_logs.logs()
        mock_client.get_logs.assert_called_once_with(query={'n': 10})

    def test_logs_query_single_snap(self, mock_client: MockClient):
        mock_client.get_logs.return_value = []
        _snapd_logs.logs('lxd')
        mock_client.get_logs.assert_called_once_with(query={'n': 10, 'names': 'lxd'})

    def test_logs_multiple_snaps(self, mock_client: MockClient):
        mock_client.get_logs.return_value = []
        _snapd_logs.logs(['lxd', 'vlc'])
        query = mock_client.get_logs.call_args.kwargs['query']
        assert query['names'] == 'lxd,vlc'

    def test_logs_arbitrary_iterable(self, mock_client: MockClient):
        # The names are iterated to validate them and then to build the query, so a generator
        # must be materialised rather than consumed by the first pass.
        mock_client.get_logs.return_value = []
        _snapd_logs.logs(s for s in ('lxd', 'vlc'))
        query = mock_client.get_logs.call_args.kwargs['query']
        assert query['names'] == 'lxd,vlc'

    def test_logs_single_element_list_is_the_same_as_a_bare_string(self, mock_client: MockClient):
        mock_client.get_logs.return_value = []
        _snapd_logs.logs(['lxd'])
        mock_client.get_logs.assert_called_once_with(query={'n': 10, 'names': 'lxd'})

    def test_logs_custom_limit(self, mock_client: MockClient):
        mock_client.get_logs.return_value = []
        _snapd_logs.logs('lxd', limit=50)
        query = mock_client.get_logs.call_args.kwargs['query']
        assert query['n'] == 50

    def test_logs_limit_none_passes_minus_one(self, mock_client: MockClient):
        mock_client.get_logs.return_value = []
        _snapd_logs.logs('lxd', limit=None)
        query = mock_client.get_logs.call_args.kwargs['query']
        assert query['n'] == -1

    @pytest.mark.parametrize('limit', [0, -1, -10])
    def test_logs_non_positive_limit_raises(self, limit: int, mock_client: MockClient):
        with pytest.raises(ValueError, match='positive integer or None'):
            _snapd_logs.logs('lxd', limit=limit)
        mock_client.get_logs.assert_not_called()

    def test_logs_parses_entries(self, mock_client: MockClient):
        mock_client.get_logs.return_value = result_of('logs_lxd.json')
        entries = _snapd_logs.logs('lxd')
        assert len(entries) == 10
        assert entries[0].sid == 'systemd'
        assert isinstance(entries[0].timestamp, datetime.datetime)

    def test_logs_pid_is_int(self, mock_client: MockClient):
        mock_client.get_logs.return_value = result_of('logs_lxd.json')
        entries = _snapd_logs.logs('lxd')
        assert entries[0].pid == 1
        assert isinstance(entries[0].pid, int)

    def test_logs_skips_malformed(self, mock_client: MockClient, caplog: LogCaptureFixture):
        mock_client.get_logs.return_value = [
            {'timestamp': '2026-04-24T03:01:19.488008Z', 'sid': 'lxd', 'pid': '1'},
            # 'message' key missing.
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
        mock_client.get_logs.return_value = []
        assert _snapd_logs.logs('lxd') == []

    def test_logs_returns_log_entry_objects(self, mock_client: MockClient):
        mock_client.get_logs.return_value = result_of('logs_lxd.json')
        entries = _snapd_logs.logs('lxd')
        assert all(isinstance(e, LogEntry) for e in entries)

    def test_log_entry_str(self, mock_client: MockClient):
        mock_client.get_logs.return_value = result_of('logs_lxd.json')
        entry = _snapd_logs.logs('lxd')[0]
        s = str(entry)
        assert str(entry.timestamp) in s
        assert str(entry.sid) in s
        assert str(entry.pid) in s
        assert str(entry.message) in s

    def test_log_entry_repr(self, mock_client: MockClient):
        mock_client.get_logs.return_value = result_of('logs_lxd.json')
        entry = _snapd_logs.logs('lxd')[0]
        r = repr(entry)
        assert entry.__class__.__name__ in r
        assert repr(entry.timestamp) in r
        assert repr(entry.sid) in r
        assert repr(entry.pid) in r
        assert repr(entry.message) in r


class TestParseTimestamp:
    def test_z_suffix(self):
        ts = parse_timestamp('2026-02-27T03:01:19.488008Z')
        assert ts.year == 2026
        assert ts.month == 2
        assert ts.day == 27
        assert ts.hour == 3

    def test_z_suffix_microseconds(self):
        ts = parse_timestamp('2026-02-27T03:01:19.488008Z')
        assert ts.microsecond == 488008

    def test_z_suffix_utc(self):
        ts = parse_timestamp('2026-02-27T03:01:19.488008Z')
        assert ts.tzinfo is not None
        assert ts.utcoffset() == datetime.timedelta(0)

    def test_z_suffix_high_precision(self):
        # 7-digit fraction should be truncated to 6 without error.
        ts = parse_timestamp('2026-02-27T03:01:19.4880089Z')
        assert ts.microsecond == 488008

    def test_z_suffix_short_fraction(self):
        # 5-digit fraction should be left-padded to 6 digits (0.13454 s = 134540 μs).
        ts = parse_timestamp('2026-02-27T03:01:19.13454Z')
        assert ts.microsecond == 134540

    def test_z_suffix_four_digit_fraction(self):
        # 4-digit fraction: 0.0033 s = 3300 μs.
        ts = parse_timestamp('2026-02-27T03:01:19.0033Z')
        assert ts.microsecond == 3300

    @pytest.mark.skipif(
        sys.version_info < (3, 11),
        reason='fromisoformat does not support offset suffixes on Python 3.10',
    )
    def test_offset_suffix(self):
        ts = parse_timestamp('2026-02-27T16:01:19.488008+13:00')
        assert ts.tzinfo is not None
        assert ts.utcoffset() == datetime.timedelta(hours=13)
        assert ts.hour == 16


class TestSnapsArgument:
    # snaps=None means system-wide logs, snaps=[] means no snaps at all, and a bare string means
    # that one snap. A string is iterable, so without the last rule 'lxd' would silently mean the
    # snaps 'l', 'x', 'd'.
    def test_none_queries_system_wide_logs(self, mock_client: MockClient):
        mock_client.get_logs.return_value = []
        _snapd_logs.logs(None)
        mock_client.get_logs.assert_called_once_with(query={'n': 10})

    def test_empty_returns_no_entries_without_a_request(self, mock_client: MockClient):
        # Unlike the /v2/apps functions, there's no separate snap argument left to check when
        # the names are empty: the names are the whole request, so nothing is asked of snapd.
        assert _snapd_logs.logs([]) == []
        mock_client.get_logs.assert_not_called()

    def test_empty_is_not_the_same_as_none(self, mock_client: MockClient):
        # The distinction the tri-state exists for: an empty collection of names must not widen
        # into a request for every snap's logs.
        mock_client.get_logs.return_value = result_of('logs_lxd.json')
        assert _snapd_logs.logs([]) == []
        assert _snapd_logs.logs(None) != []

    def test_empty_still_validates_the_limit(self, mock_client: MockClient):
        # Arguments are validated even when there's no work to do, so a bad limit is an error
        # either way rather than depending on how many snaps were named.
        with pytest.raises(ValueError, match='positive integer or None'):
            _snapd_logs.logs([], limit=0)
        mock_client.get_logs.assert_not_called()

    def test_empty_string_is_not_empty_snaps(self, mock_client: MockClient):
        # The one case the bare-string rule makes ambiguous: '' is one (unusable) snap name, not
        # an empty collection of them, so it's a ValueError rather than an empty result.
        with pytest.raises(ValueError, match='must not be empty'):
            _snapd_logs.logs('')
        mock_client.get_logs.assert_not_called()


class TestUnsafeSnapName:
    # The names are sent as one comma-separated query parameter, and snapd's parsing of it drops
    # blank entries, splits on commas, and strips whitespace -- so a name it alters is silently
    # not the query the caller asked for, rather than an error (pinned by the functional tests).
    # We reject anything that parsing would alter before making the request.
    @pytest.mark.parametrize(
        ('name', 'match'),
        [
            ('', 'must not be empty'),
            (' ', 'must not be blank'),
            ('\t', 'must not be blank'),
            (',', 'must not contain a comma'),
            ('lxd,vlc', 'must not contain a comma'),
            (' lxd', 'must not have leading or trailing whitespace'),
            ('lxd\n', 'must not have leading or trailing whitespace'),
        ],
    )
    def test_unsafe_name_raises_value_error_without_request(
        self, mock_client: MockClient, name: str, match: str
    ):
        with pytest.raises(ValueError, match=match):
            _snapd_logs.logs(name)
        mock_client.get_logs.assert_not_called()

    @pytest.mark.parametrize('name', ['', ' ', 'lxd,vlc', ' lxd'])
    def test_unsafe_name_among_valid_names_raises(self, mock_client: MockClient, name: str):
        with pytest.raises(ValueError):
            _snapd_logs.logs(['lxd', name])
        mock_client.get_logs.assert_not_called()

    def test_name_validated_before_limit(self, mock_client: MockClient):
        with pytest.raises(ValueError, match='must not be empty'):
            _snapd_logs.logs('', limit=0)
        mock_client.get_logs.assert_not_called()
