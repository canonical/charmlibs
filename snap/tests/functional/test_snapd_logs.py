#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_logs: logs."""

import pytest

from charmlibs.snap import _client, _errors, _snapd_logs
from conftest import ensure_installed_local

# Locally-built snaps (tests/functional/snaps). The service snaps run a daemon that emits a
# fixed burst of lines on startup, so the number of entries available to read is a property of
# the fixture rather than of how chatty some real-world snap happens to be.
_SNAP = 'test-service-snap'
_OTHER_SNAP = 'test-other-service-snap'
# A snap with no apps at all, so snapd reports it has no services.
_NO_SERVICES_SNAP = 'test-snap'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
# Two distinct names are needed to show that a comma in one name queries two snaps.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'
_ABSENT_SNAP_2 = 'this-snap-also-does-not-exist-def-456'


# ---------------------------------------------------------------------------
# logs (service snap installed)
# ---------------------------------------------------------------------------


def test_logs_returns_log_entries():
    ensure_installed_local(_SNAP)
    entries = _snapd_logs.logs(_SNAP, limit=5)
    assert isinstance(entries, list)


def test_logs_entries_have_expected_fields():
    ensure_installed_local(_SNAP)
    entries = _snapd_logs.logs(_SNAP, limit=5)
    for entry in entries:
        assert isinstance(entry, _snapd_logs.LogEntry)
        assert entry.timestamp
        assert isinstance(entry.message, str)
        assert isinstance(entry.sid, str)
        assert isinstance(entry.pid, int)


def test_logs_limit():
    # The limit parameter limits the number of results returned.
    ensure_installed_local(_SNAP)
    entries = _snapd_logs.logs(_SNAP, limit=3)
    assert len(entries) <= 3


def test_logs_limit_above_default():
    # The limit parameter is not capped at the snapd default of 10: requesting more
    # returns more (provided enough log entries are available).
    ensure_installed_local(_SNAP)
    entries = _snapd_logs.logs(_SNAP, limit=50)
    # The daemon emits a burst of 60 lines on startup, so there are always more than 10.
    assert len(entries) > 10


def test_logs_ordered_oldest_first():
    # Log entries are returned in chronological order: oldest first, newest last.
    ensure_installed_local(_SNAP)
    entries = _snapd_logs.logs(_SNAP, limit=50)
    timestamps = [entry.timestamp for entry in entries]
    assert timestamps == sorted(timestamps)


def test_logs_multiple_snaps():
    # Requesting logs for multiple snaps should not raise.
    ensure_installed_local(_SNAP)
    ensure_installed_local(_OTHER_SNAP)
    entries = _snapd_logs.logs([_SNAP, _OTHER_SNAP], limit=10)
    assert isinstance(entries, list)


def test_logs_bare_name_and_single_element_list_agree():
    # A bare string is one snap name, not an iterable of its characters, so it queries the same
    # logs as the same name in a list. Compared by syslog identifier, since new entries are
    # logged all the time.
    ensure_installed_local(_SNAP)
    from_string = {entry.sid for entry in _snapd_logs.logs(_SNAP, limit=None)}
    from_list = {entry.sid for entry in _snapd_logs.logs([_SNAP], limit=None)}
    assert from_string
    assert from_list.issuperset(from_string)


def test_logs_limit_zero_raises():
    # A non-positive limit is rejected client-side with a ValueError.
    with pytest.raises(ValueError, match='positive integer or None'):
        _snapd_logs.logs(_SNAP, limit=0)


def test_logs_limit_none_returns_all():
    # limit=None retrieves all available log entries (no limit).
    ensure_installed_local(_SNAP)
    all_entries = _snapd_logs.logs(_SNAP, limit=None)
    limited = _snapd_logs.logs(_SNAP, limit=5)
    assert isinstance(all_entries, list)
    assert len(all_entries) >= len(limited)


def test_logs_no_snap_args():
    # Calling logs() with no snap arguments returns system-wide logs.
    entries = _snapd_logs.logs(limit=3)
    assert isinstance(entries, list)


# ---------------------------------------------------------------------------
# snaps=[] ("no snaps") vs snaps=None ("system-wide")
# ---------------------------------------------------------------------------


def test_logs_empty_snaps_returns_no_entries():
    # The distinction the tri-state exists for: an empty list of names must not widen into a
    # request for every snap's logs, which is what dropping the 'names' parameter would do (and
    # what snapd does with a 'names' value that parses away -- see the raw tests below).
    ensure_installed_local(_SNAP)
    assert _snapd_logs.logs([], limit=None) == []
    assert _snapd_logs.logs(None, limit=None) != []


def test_logs_empty_snaps_still_validates_the_limit():
    # Arguments are validated even when there's no work to do, so a bad limit is an error either
    # way rather than depending on how many snaps were named.
    with pytest.raises(ValueError, match='positive integer or None'):
        _snapd_logs.logs([], limit=0)


# ---------------------------------------------------------------------------
# snap with no services
# ---------------------------------------------------------------------------


def test_logs_snap_with_no_services_raises():
    # A snap with no services raises AppNotFoundError.
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_logs.logs(_NO_SERVICES_SNAP)
    assert ctx.value._kind == 'app-not-found'


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_logs_not_installed_snap_raises():
    # Requesting logs for an uninstalled snap raises _NotFoundError.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_logs.logs(_ABSENT_SNAP)
    assert ctx.value._kind == 'snap-not-found'


# ---------------------------------------------------------------------------
# names that snapd's 'names' parsing would alter
#
# logs() rejects these client-side, so most go through _client to pin what snapd does with the
# query that rejection stops us from sending. It doesn't reject any of them: it splits 'names'
# on commas, strips whitespace from each entry, and drops the ones left empty, so an unusable
# name is not an error but a silent change to which logs you get -- the reason we don't pass
# one through.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'name',
    [
        '',
        ' ',
        '\t',
        '\xa0',
        f'{_NO_SERVICES_SNAP},{_SNAP}',
        f' {_NO_SERVICES_SNAP}',
        f'{_NO_SERVICES_SNAP}\n',
    ],
)
def test_unusable_names_raise_value_error(name: str):
    # The public contract: anything snapd's parsing would alter is a ValueError, not a request.
    with pytest.raises(ValueError):
        _snapd_logs.logs(name)


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
    ensure_installed_local(_SNAP)
    unfiltered = {entry['sid'] for entry in _client.get_logs(query={'n': -1})}
    assert unfiltered, 'no system-wide logs to compare against'
    result = {entry['sid'] for entry in _client.get_logs(query={'n': -1, 'names': names})}
    assert result.issuperset(unfiltered)


@pytest.mark.parametrize('names', [' ', '\t', '\xa0', ' , '])
def test_blank_names_leave_no_filter(names: str):
    # Whitespace is stripped from each entry before the empty ones are dropped, so a blank name
    # is discarded exactly like an empty one and widens the query in the same way. Python's
    # str.strip and the Go unicode.IsSpace snapd strips with agree on which characters these are,
    # including U+00A0, which the two define separately -- so the client-side check can mirror
    # snapd's rule rather than approximate it.
    ensure_installed_local(_SNAP)
    unfiltered = {entry['sid'] for entry in _client.get_logs(query={'n': -1})}
    assert unfiltered, 'no system-wide logs to compare against'
    result = {entry['sid'] for entry in _client.get_logs(query={'n': -1, 'names': names})}
    assert result.issuperset(unfiltered)


@pytest.mark.parametrize(
    'names',
    [
        f',{_NO_SERVICES_SNAP}',
        f'{_NO_SERVICES_SNAP},',
        f',{_NO_SERVICES_SNAP},',
        f' {_NO_SERVICES_SNAP} ',
        f'\t{_NO_SERVICES_SNAP}\n',
        f' ,{_NO_SERVICES_SNAP}',
    ],
)
def test_discarded_and_stripped_entries_leave_the_named_snap(names: str):
    # The named snap is all that is left once the empty entries are dropped and the surviving
    # ones are stripped, so these queries mean what naming it on its own means: snapd resolves
    # the name and reports that it has no services. An empty entry taken as a name of its own,
    # or a padded name taken literally, would report something else.
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.get_logs(query={'n': -1, 'names': names})
    assert ctx.value._kind == 'app-not-found'
    assert ctx.value.message == f'snap "{_NO_SERVICES_SNAP}" has no services'


def test_comma_in_a_name_queries_two_snaps():
    # A comma inside one name is not escaped by url-encoding it: snapd decodes the parameter
    # before splitting, so one name becomes two -- which is why a comma is rejected rather than
    # passed through. Which of the two snapd then blames is its own business, and isn't
    # positional (swapping the names doesn't swap the error), so this pins only that the name
    # was split: the error is about one of the halves, never about the name as passed.
    names = f'{_ABSENT_SNAP},{_ABSENT_SNAP_2}'
    with pytest.raises(_errors._NotFoundError) as ctx:
        _client.get_logs(query={'n': -1, 'names': names})
    assert ctx.value._kind == 'snap-not-found'
    assert ctx.value._value in (_ABSENT_SNAP, _ABSENT_SNAP_2)
    assert names not in str(ctx.value)


def test_no_comma_in_a_name_is_one_snap():
    # The control for the test above: without a comma the whole string is one name, so an error
    # about a name as passed is what a comma-free name looks like.
    with pytest.raises(_errors._NotFoundError) as ctx:
        _client.get_logs(query={'n': -1, 'names': _ABSENT_SNAP})
    assert ctx.value._value == _ABSENT_SNAP
