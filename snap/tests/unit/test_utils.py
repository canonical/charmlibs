# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _utils
from charmlibs.snap._errors import NotFoundError

if TYPE_CHECKING:
    from conftest import MockClient


# Every whitespace character we've checked snapd's Go implementation against, including the
# ones Python and Go define separately. See get_err_if_not_comma_list_safe.
BLANK = [' ', '  ', '\t', '\n', '\r', '\x0b', '\x0c', '\x85', '\xa0', '\u1680', '\u2000', '\u3000']
# Zero-width characters are content to both Python and snapd, not whitespace.
ZERO_WIDTH = ['\u200b', '\ufeff']


def assert_err(err: ValueError | None, match: str) -> None:
    """Assert an error was returned (not raised) and its message matches."""
    assert isinstance(err, ValueError)
    assert re.search(match, str(err)), f'{str(err)!r} does not match {match!r}'


class TestGetErrIfEmptyOrBlank:
    def test_empty_returns_error(self):
        assert_err(_utils.get_err_if_empty_or_blank('', label='snap name'), 'must not be empty')

    @pytest.mark.parametrize('value', BLANK)
    def test_blank_returns_error(self, value: str):
        assert_err(_utils.get_err_if_empty_or_blank(value, label='snap name'), 'must not be blank')

    def test_blank_error_names_the_value(self):
        # The value is shown as a repr: without it, the message for a blank value says nothing
        # about what was passed, and ' ' and '\t' look identical.
        err = _utils.get_err_if_empty_or_blank('\t', label='snap name')
        assert str(err) == "snap name must not be blank: '\\t'"

    def test_label_is_used_in_the_message(self):
        assert_err(_utils.get_err_if_empty_or_blank('', label='config key'), 'config key must not')

    @pytest.mark.parametrize(
        'value', ['hello-world', 'lxd', '..', 'a/b', 'a b', ' a', *ZERO_WIDTH]
    )
    def test_other_values_return_none(self, value: str):
        # Only emptiness and blankness are checked here -- names that aren't usable in a path are
        # the business of snap_path_segment, and padding is only a problem for the endpoints
        # covered by get_err_if_not_comma_list_safe.
        assert _utils.get_err_if_empty_or_blank(value, label='snap name') is None

    def test_no_values_returns_none(self):
        # Callers unpack a possibly-empty collection of values into the call.
        assert _utils.get_err_if_empty_or_blank(label='config key') is None

    def test_all_values_are_checked(self):
        assert _utils.get_err_if_empty_or_blank('a', 'b', label='config key') is None
        assert_err(_utils.get_err_if_empty_or_blank('a', '', label='config key'), 'not be empty')

    def test_the_first_failing_value_is_reported(self):
        err = _utils.get_err_if_empty_or_blank('a', ' ', '', label='config key')
        assert_err(err, 'must not be blank')


class TestGetErrIfBlank:
    def test_empty_returns_none(self):
        # The interface functions give an empty value a meaning of its own.
        assert _utils.get_err_if_blank('', label='slot snap name') is None

    @pytest.mark.parametrize('value', BLANK)
    def test_blank_returns_error(self, value: str):
        assert_err(_utils.get_err_if_blank(value, label='slot snap name'), 'slot snap name must')

    @pytest.mark.parametrize('value', ['hello-world', 'a b', ' a', *ZERO_WIDTH])
    def test_other_values_return_none(self, value: str):
        assert _utils.get_err_if_blank(value, label='slot snap name') is None

    def test_all_values_are_checked(self):
        assert _utils.get_err_if_blank('', 'a', label='slot name') is None
        assert_err(_utils.get_err_if_blank('', ' ', label='slot name'), 'must not be blank')


def comma_separated_list(value: str) -> list[str]:
    """Mirror of snapd's strutil.CommaSeparatedList, as verified against the real API.

    Splits on commas, strips whitespace from each field, and discards the empty ones.
    """
    return [stripped for field in value.split(',') if (stripped := field.strip())]


# The contract get_err_if_not_comma_list_safe exists to enforce: a value snapd's parser gives
# back unchanged is accepted, and anything else is rejected. Asserting that against a mirror of
# the parser keeps the individual checks in the function honest as a set.
SAFE = ['hello-world', 'lxd', 'a.b', 'a b', 'core24', *ZERO_WIDTH]
UNSAFE = ['', *BLANK, ',', ',,', 'a,b', ' , ', ' a', 'a ', '\ta\n']


class TestGetErrIfNotCommaListSafe:
    @pytest.mark.parametrize('value', SAFE)
    def test_safe_values_round_trip_through_the_parser(self, value: str):
        assert comma_separated_list(value) == [value]

    @pytest.mark.parametrize('value', UNSAFE)
    def test_unsafe_values_do_not_round_trip_through_the_parser(self, value: str):
        assert comma_separated_list(value) != [value]

    @pytest.mark.parametrize('value', SAFE)
    def test_safe_values_return_none(self, value: str):
        assert _utils.get_err_if_not_comma_list_safe(value, label='snap name') is None

    @pytest.mark.parametrize('value', UNSAFE)
    def test_unsafe_values_return_an_error(self, value: str):
        assert isinstance(
            _utils.get_err_if_not_comma_list_safe(value, label='snap name'), ValueError
        )

    @pytest.mark.parametrize(
        ('value', 'match'),
        [
            ('', 'must not be empty'),
            (' ', 'must not be blank'),
            (',', 'must not contain a comma'),
            ('a,b', 'must not contain a comma'),
            (' a', 'must not have leading or trailing whitespace'),
            ('a\n', 'must not have leading or trailing whitespace'),
        ],
    )
    def test_each_way_of_failing_has_its_own_message(self, value: str, match: str):
        assert_err(_utils.get_err_if_not_comma_list_safe(value, label='snap name'), match)

    def test_all_values_are_checked(self):
        assert _utils.get_err_if_not_comma_list_safe('a', 'b', label='snap name') is None
        err = _utils.get_err_if_not_comma_list_safe('a', 'b,c', label='snap name')
        assert_err(err, 'must not contain a comma')


class TestSnapPathSegment:
    @pytest.mark.parametrize('snap', ['hello-world', 'lxd', 'kube-proxy', 'core24', 'foo_bar'])
    def test_ordinary_names_pass_through_unchanged(self, snap: str):
        assert _utils.snap_path_segment(snap) == snap

    def test_empty_raises(self):
        with pytest.raises(ValueError, match='must not be empty'):
            _utils.snap_path_segment('')

    @pytest.mark.parametrize('snap', ['.', '..', '/', 'a/b', 'hello-world/conf', '../changes/1'])
    def test_non_segment_names_raise(self, snap: str):
        # Percent-encoding can't make these safe: snapd's router matches on the decoded path,
        # so '%2F' is still a separator to it, and quote() leaves '.' unencoded. See the
        # functional tests for what snapd does with the paths these would otherwise build.
        with pytest.raises(ValueError, match='single path segment'):
            _utils.snap_path_segment(snap)

    @pytest.mark.parametrize(
        ('snap', 'expected'),
        [
            ('hello world', 'hello%20world'),
            ('hello?keys=x', 'hello%3Fkeys%3Dx'),
            ('hello#frag', 'hello%23frag'),
            ('hello%2Fworld', 'hello%252Fworld'),
        ],
    )
    def test_other_special_characters_are_encoded(self, snap: str, expected: str):
        # These can't change which endpoint we reach once encoded, so they're passed to snapd
        # (which answers with snap-not-found) rather than rejected.
        assert _utils.snap_path_segment(snap) == expected


class TestCheckInstalledOrSystem:
    def test_empty_raises_value_error_without_request(self, mock_client: MockClient):
        with pytest.raises(ValueError, match='must not be empty'):
            _utils.check_installed_or_system('')
        mock_client.get.assert_not_called()

    @pytest.mark.parametrize('snap', ['system', 'core'])
    def test_system_names_are_not_probed(self, snap: str, mock_client: MockClient):
        assert _utils.check_installed_or_system(snap) is None
        mock_client.get.assert_not_called()

    def test_installed_snap_is_probed(self, mock_client: MockClient):
        assert _utils.check_installed_or_system('hello world') is None
        mock_client.get.assert_called_once_with('/v2/snaps/hello%20world')

    def test_absent_snap_returns_not_found(self, mock_client: MockClient):
        error = NotFoundError('snap not installed', kind='snap-not-found', value='hello-world')
        mock_client.get.side_effect = error
        assert _utils.check_installed_or_system('hello-world') is error
