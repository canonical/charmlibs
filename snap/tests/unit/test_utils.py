# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _utils
from charmlibs.snap._errors import NotFoundError

if TYPE_CHECKING:
    from conftest import MockClient


# Every whitespace character we've checked snapd's Go implementation against, including the
# ones Python and Go define separately. See comma_list.
BLANK = [' ', '  ', '\t', '\n', '\r', '\x0b', '\x0c', '\x85', '\xa0', '\u1680', '\u2000', '\u3000']
# Zero-width characters are content to both Python and snapd, not whitespace.
ZERO_WIDTH = ['\u200b', '\ufeff']


class TestEmptyOrBlank:
    def test_empty(self):
        assert _utils.empty_or_blank('') == 'must not be empty'

    @pytest.mark.parametrize('value', BLANK)
    def test_blank(self, value: str):
        assert _utils.empty_or_blank(value) == f'must not be blank: {value!r}'

    def test_blank_phrase_quotes_the_value(self):
        # A blank value is invisible without the repr, and ' ' and '\t' read identically.
        assert _utils.empty_or_blank('\t') == "must not be blank: '\\t'"

    @pytest.mark.parametrize(
        'value', ['hello-world', 'lxd', '..', 'a/b', 'a b', ' a', *ZERO_WIDTH]
    )
    def test_usable_values(self, value: str):
        # Only emptiness and blankness are checked here -- names that aren't usable in a path are
        # the business of snap_path_segment, and padding is only a problem for the endpoints
        # covered by comma_list.
        assert _utils.empty_or_blank(value) is None


class TestOneValueOrMany:
    # Each check takes one value or an iterable of them, so the caller can hand over the whole
    # collection it was given and keep the loop out of the call site.
    def test_a_bare_string_is_one_value_not_an_iterable_of_characters(self):
        # ' a' is not blank, but its characters are: iterating it would report the wrong problem.
        assert _utils.empty_or_blank(' a') is None
        assert _utils.comma_list('ab') is None

    def test_first_unusable_value_is_described(self):
        assert _utils.empty_or_blank(['a', ' ', '']) == "must not be blank: ' '"
        assert _utils.comma_list(['a', 'b,c']) == "must not contain a comma: 'b,c'"

    def test_all_usable_values(self):
        assert _utils.empty_or_blank(['a', 'b']) is None
        assert _utils.comma_list(('a', 'b')) is None

    def test_no_values(self):
        # Callers pass collections that may be empty (keys=[], no services, no snap names).
        assert _utils.empty_or_blank([]) is None
        assert _utils.comma_list(()) is None

    def test_a_dict_is_checked_by_its_keys(self):
        # set() hands over its config mapping directly.
        assert _utils.empty_or_blank({'a': 1, 'b': 2}) is None
        assert _utils.empty_or_blank({'a': 1, '': 2}) == 'must not be empty'


class TestBlank:
    def test_empty_is_not_a_problem(self):
        # The interface functions give an empty value a meaning of its own.
        assert _utils.blank('') is None

    @pytest.mark.parametrize('value', BLANK)
    def test_blank(self, value: str):
        assert _utils.blank(value) == f'must not be blank: {value!r}'

    @pytest.mark.parametrize('value', ['hello-world', 'a b', ' a', *ZERO_WIDTH])
    def test_usable_values(self, value: str):
        assert _utils.blank(value) is None


def comma_separated_list(value: str) -> list[str]:
    """Mirror of snapd's strutil.CommaSeparatedList, as verified against the real API.

    Splits on commas, strips whitespace from each field, and discards the empty ones.
    """
    return [stripped for field in value.split(',') if (stripped := field.strip())]


# The contract comma_list exists to enforce: a value snapd's parser gives back unchanged
# is fine, and anything else is a problem. Asserting that against a mirror of the parser keeps
# the individual checks in the function honest as a set.
SAFE = ['hello-world', 'lxd', 'a.b', 'a b', 'core24', *ZERO_WIDTH]
UNSAFE = ['', *BLANK, ',', ',,', 'a,b', ' , ', ' a', 'a ', '\ta\n']


class TestCommaList:
    @pytest.mark.parametrize('value', SAFE)
    def test_safe_values_round_trip_through_the_parser(self, value: str):
        assert comma_separated_list(value) == [value]

    @pytest.mark.parametrize('value', UNSAFE)
    def test_unsafe_values_do_not_round_trip_through_the_parser(self, value: str):
        assert comma_separated_list(value) != [value]

    @pytest.mark.parametrize('value', SAFE)
    def test_safe_values_have_no_problem(self, value: str):
        assert _utils.comma_list(value) is None

    @pytest.mark.parametrize('value', UNSAFE)
    def test_unsafe_values_have_a_problem(self, value: str):
        assert _utils.comma_list(value) is not None

    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            ('', 'must not be empty'),
            (' ', "must not be blank: ' '"),
            (',', "must not contain a comma: ','"),
            ('a,b', "must not contain a comma: 'a,b'"),
            (' a', "must not have leading or trailing whitespace: ' a'"),
            ('a\n', "must not have leading or trailing whitespace: 'a\\n'"),
        ],
    )
    def test_each_way_of_failing_has_its_own_phrase(self, value: str, expected: str):
        assert _utils.comma_list(value) == expected

    def test_phrases_read_as_a_sentence_after_a_noun(self):
        # The phrases are written to follow the name of the thing being checked, which is what
        # lets each call site supply its own noun and context.
        problem = _utils.comma_list('a,b')
        assert f'config key {problem}' == "config key must not contain a comma: 'a,b'"


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
