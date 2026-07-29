# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _utils
from charmlibs.snap._errors import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from conftest import MockClient


# Every whitespace character we've checked snapd's Go implementation against, including the
# ones Python and Go define separately. See comma_list.
BLANK = [' ', '  ', '\t', '\n', '\r', '\x0b', '\x0c', '\x85', '\xa0', '\u1680', '\u2000', '\u3000']
# Zero-width characters are content to both Python and snapd, not whitespace.
ZERO_WIDTH = ['\u200b', '\ufeff']


class TestPredicates:
    # Each predicate answers one question about one value, so the checks below can spell out the
    # rules they apply as a chain rather than deferring to each other.
    @pytest.mark.parametrize(
        ('predicate', 'value', 'expected'),
        [
            (_utils._empty, '', 'must not be empty'),
            (_utils._empty, ' ', None),
            (_utils._empty, 'a', None),
            (_utils._blank, '', None),  # Left to _empty, so check_blank can omit it.
            (_utils._blank, ' ', "must not be blank: ' '"),
            (_utils._blank, 'a', None),
            (_utils._comma, 'a,b', "must not contain a comma: 'a,b'"),
            (_utils._comma, 'a', None),
            (_utils._padding, ' a', "must not have leading or trailing whitespace: ' a'"),
            (_utils._padding, 'a b', None),
            (_utils._path_segment, 'a/b', "must be a single path segment: 'a/b'"),
            (_utils._path_segment, '.', "must be a single path segment: '.'"),
            (_utils._path_segment, '..', "must be a single path segment: '..'"),
            (_utils._path_segment, 'a.b', None),  # Only '.' and '..' are non-canonical.
        ],
    )
    def test_predicate(
        self, predicate: Callable[[str], str | None], value: str, expected: str | None
    ):
        assert predicate(value) == expected


def assert_raises(call: Callable[[], None], expected: str) -> None:
    """Assert the check raises ValueError with exactly the expected message."""
    with pytest.raises(ValueError) as ctx:
        call()
    assert str(ctx.value) == expected


class TestRaiseIfEmptyOrBlank:
    def test_empty(self):
        assert_raises(
            lambda: _utils.raise_if_empty_or_blank('', label='snap name'),
            'snap name must not be empty',
        )

    @pytest.mark.parametrize('value', BLANK)
    def test_blank(self, value: str):
        assert_raises(
            lambda: _utils.raise_if_empty_or_blank(value, label='snap name'),
            f'snap name must not be blank: {value!r}',
        )

    def test_label_names_the_value(self):
        assert_raises(
            lambda: _utils.raise_if_empty_or_blank('', label='config key'),
            'config key must not be empty',
        )

    @pytest.mark.parametrize(
        'value', ['hello-world', 'lxd', '..', 'a/b', 'a b', ' a', *ZERO_WIDTH]
    )
    def test_usable_values_do_not_raise(self, value: str):
        # Only emptiness and blankness are checked here -- names that aren't usable in a path are
        # the business of snap_path_segment, and padding is only a problem for the endpoints
        # covered by raise_if_not_comma_list_safe.
        _utils.raise_if_empty_or_blank(value, label='snap name')


class TestOneValueOrMany:
    # Each check takes one value or a collection of them, so the caller can hand over the whole
    # collection it was given and keep the loop out of the call site.
    def test_a_bare_string_is_one_value_not_a_collection_of_characters(self):
        # ' a' is not blank, but its characters are: iterating it would report the wrong problem.
        _utils.raise_if_empty_or_blank(' a', label='snap name')
        _utils.raise_if_not_comma_list_safe('ab', label='snap name')

    def test_first_unusable_value_is_reported(self):
        assert_raises(
            lambda: _utils.raise_if_empty_or_blank(['a', ' ', ''], label='config key'),
            "config key must not be blank: ' ' (in ['a', ' ', ''])",
        )

    def test_all_usable_values_do_not_raise(self):
        _utils.raise_if_empty_or_blank(['a', 'b'], label='config key')
        _utils.raise_if_not_comma_list_safe(('a', 'b'), label='snap name')

    def test_no_values_does_not_raise(self):
        # Callers pass collections that may be empty (keys=[], no services, no snap names).
        _utils.raise_if_empty_or_blank([], label='config key')
        _utils.raise_if_not_comma_list_safe((), label='snap name')

    def test_a_dict_is_checked_by_its_keys(self):
        # set() hands over its config mapping directly.
        _utils.raise_if_empty_or_blank({'a': 1, 'b': 2}, label='config key')
        assert_raises(
            lambda: _utils.raise_if_empty_or_blank({'a': 1, '': 2}, label='config key'),
            "config key must not be empty (in ['a', ''])",
        )

    def test_a_dicts_values_are_never_in_the_message(self):
        # The config a charm sets can hold secrets, and the error reaches the Juju debug log.
        with pytest.raises(ValueError) as ctx:
            _utils.raise_if_empty_or_blank({'password': 'hunter2', '': 1}, label='config key')
        assert 'hunter2' not in str(ctx.value)


class TestMessageContext:
    # The collection is named only when there was more than one value to pick from: for a single
    # value the phrase already quotes it, and repeating it reads as noise.
    def test_one_value_is_not_repeated(self):
        assert_raises(
            lambda: _utils.raise_if_empty_or_blank([' '], label='snap name'),
            "snap name must not be blank: ' '",
        )

    def test_many_values_are_named(self):
        assert_raises(
            lambda: _utils.raise_if_empty_or_blank(['a', ' '], label='snap name'),
            "snap name must not be blank: ' ' (in ['a', ' '])",
        )


class TestRaiseIfBlank:
    def test_empty_does_not_raise(self):
        # The interface functions give an empty value a meaning of its own.
        _utils.raise_if_blank('', label='slot snap name')

    @pytest.mark.parametrize('value', BLANK)
    def test_blank(self, value: str):
        assert_raises(
            lambda: _utils.raise_if_blank(value, label='slot snap name'),
            f'slot snap name must not be blank: {value!r}',
        )

    @pytest.mark.parametrize('value', ['hello-world', 'a b', ' a', *ZERO_WIDTH])
    def test_usable_values_do_not_raise(self, value: str):
        _utils.raise_if_blank(value, label='slot snap name')


def comma_separated_list(value: str) -> list[str]:
    """Mirror of snapd's strutil.CommaSeparatedList, as verified against the real API.

    Splits on commas, strips whitespace from each field, and discards the empty ones.
    """
    return [stripped for field in value.split(',') if (stripped := field.strip())]


# The contract raise_if_not_comma_list_safe exists to enforce: a value snapd's parser gives back
# unchanged is fine, and anything else is rejected. Asserting that against a mirror of the parser
# keeps the individual predicates in the chain honest as a set.
SAFE = ['hello-world', 'lxd', 'a.b', 'a b', 'core24', *ZERO_WIDTH]
UNSAFE = ['', *BLANK, ',', ',,', 'a,b', ' , ', ' a', 'a ', '\ta\n']


class TestRaiseIfNotCommaListSafe:
    @pytest.mark.parametrize('value', SAFE)
    def test_safe_values_round_trip_through_the_parser(self, value: str):
        assert comma_separated_list(value) == [value]

    @pytest.mark.parametrize('value', UNSAFE)
    def test_unsafe_values_do_not_round_trip_through_the_parser(self, value: str):
        assert comma_separated_list(value) != [value]

    @pytest.mark.parametrize('value', SAFE)
    def test_safe_values_do_not_raise(self, value: str):
        _utils.raise_if_not_comma_list_safe(value, label='snap name')

    @pytest.mark.parametrize('value', UNSAFE)
    def test_unsafe_values_raise(self, value: str):
        with pytest.raises(ValueError):
            _utils.raise_if_not_comma_list_safe(value, label='snap name')

    @pytest.mark.parametrize(
        ('value', 'expected'),
        [
            ('', 'snap name must not be empty'),
            (' ', "snap name must not be blank: ' '"),
            (',', "snap name must not contain a comma: ','"),
            ('a,b', "snap name must not contain a comma: 'a,b'"),
            (' a', "snap name must not have leading or trailing whitespace: ' a'"),
            ('a\n', "snap name must not have leading or trailing whitespace: 'a\\n'"),
        ],
    )
    def test_each_way_of_failing_has_its_own_message(self, value: str, expected: str):
        assert_raises(
            lambda: _utils.raise_if_not_comma_list_safe(value, label='snap name'), expected
        )

    def test_each_value_is_checked_completely_before_the_next(self):
        # The first unusable value is reported, not the most severe problem across all of them:
        # what gets reported for a value doesn't depend on what comes after it.
        assert_raises(
            lambda: _utils.raise_if_not_comma_list_safe(['a,b', ''], label='snap name'),
            "snap name must not contain a comma: 'a,b' (in ['a,b', ''])",
        )
        assert_raises(
            lambda: _utils.raise_if_not_comma_list_safe(['', 'a,b'], label='snap name'),
            "snap name must not be empty (in ['', 'a,b'])",
        )


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


class TestAsList:
    @pytest.mark.parametrize(
        ('values', 'expected'),
        [
            ('abc', ['abc']),
            ('', ['']),  # Emptiness is the checks' business, not this function's.
            ([], []),
            (['a', 'b'], ['a', 'b']),
            (('a', 'b'), ['a', 'b']),
            ({'a': 1, 'b': 2}, ['a', 'b']),  # A mapping iterates its keys.
            # Callers iterate the values twice -- to validate them and then to send them -- so
            # a one-shot iterable must come back materialised rather than passed through.
            ((c for c in ('a', 'b')), ['a', 'b']),
        ],
    )
    def test_as_list(self, values: str | Iterable[str], expected: list[str]):
        assert _utils.as_list(values) == expected


class TestCheckInstalled:
    def test_empty_raises_value_error_without_request(self, mock_client: MockClient):
        with pytest.raises(ValueError, match='must not be empty'):
            _utils.check_installed('')
        mock_client.get.assert_not_called()

    @pytest.mark.parametrize('snap', ['system', 'core'])
    def test_system_names_are_not_probed_when_skipped(self, snap: str, mock_client: MockClient):
        assert _utils.check_installed(snap, skip_system=True) is None
        mock_client.get.assert_not_called()

    @pytest.mark.parametrize('snap', ['system', 'core'])
    def test_system_names_are_probed_by_default(self, snap: str, mock_client: MockClient):
        # skip_system is for endpoints snapd serves under these names whether or not the core
        # snap is installed. Elsewhere -- /v2/apps -- they get no special treatment, so an
        # absent 'core' (and 'system', which is never a snap) is reported as not installed.
        error = NotFoundError('snap not installed', kind='snap-not-found', value=snap)
        mock_client.get.side_effect = error
        assert _utils.check_installed(snap) is error
        mock_client.get.assert_called_once_with(f'/v2/snaps/{snap}')

    def test_installed_snap_is_probed(self, mock_client: MockClient):
        assert _utils.check_installed('hello world') is None
        mock_client.get.assert_called_once_with('/v2/snaps/hello%20world')

    def test_absent_snap_returns_not_found(self, mock_client: MockClient):
        error = NotFoundError('snap not installed', kind='snap-not-found', value='hello-world')
        mock_client.get.side_effect = error
        assert _utils.check_installed('hello-world') is error


class TestNormalizeChannel:
    @pytest.mark.parametrize(
        ('channel', 'expected'),
        [
            ('', ''),
            ('/', ''),
            ('stable', 'latest/stable'),
            ('candidate', 'latest/candidate'),
            ('beta', 'latest/beta'),
            ('edge', 'latest/edge'),
            ('mytrack', 'mytrack/stable'),
            ('latest', 'latest/stable'),
            ('latest/stable', 'latest/stable'),
            ('latest/stable/hotfix', 'latest/stable/hotfix'),
            ('3/stable', '3/stable'),
            ('3.6/edge', '3.6/edge'),
            # A leading risk in a two part channel means the second part is a branch, so the
            # default track is filled in -- 'edge/hotfix' is not the 'hotfix' risk on track 'edge'.
            ('edge/hotfix', 'latest/edge/hotfix'),
        ],
    )
    def test_normalize(self, channel: str, expected: str):
        assert _utils.normalize_channel(channel) == expected


class TestResolveChannel:
    @pytest.mark.parametrize(
        ('channel', 'tracking', 'expected'),
        [
            # No requested channel keeps whatever the snap is on.
            ('', 'latest/stable', 'latest/stable'),
            ('', '', ''),
            # Not installed (or installed from a local file): nothing to inherit a track from.
            ('edge', '', 'latest/edge'),
            ('3.6', '', '3.6/stable'),
            # A risk inherits the track the snap is on.
            ('edge', 'latest/stable', 'latest/edge'),
            ('edge', '3.6/stable', '3.6/edge'),
            ('stable', '3.6/edge', '3.6/stable'),
            ('edge/hotfix', '3.6/stable', '3.6/edge/hotfix'),
            # A track doesn't inherit the risk: it takes the default risk instead.
            ('4.0', '3.6/edge', '4.0/stable'),
            # A fully specified channel is used as given.
            ('4.0/edge', '3.6/stable', '4.0/edge'),
            ('latest/edge', '3.6/stable', 'latest/edge'),
        ],
    )
    def test_resolve(self, channel: str, tracking: str, expected: str):
        assert _utils.resolve_channel(channel, tracking) == expected

    @pytest.mark.parametrize('channel', ['stable', 'candidate', 'beta', 'edge'])
    def test_resolving_the_tracked_channel_is_a_no_op(self, channel: str):
        # ensure() relies on this to tell whether a requested channel is the one already
        # tracked, so resolving a snap's own channel must give that channel back unchanged.
        for track in ('latest', '3.6'):
            tracking = f'{track}/{channel}'
            assert _utils.resolve_channel(channel, tracking) == tracking
            assert _utils.resolve_channel(tracking, tracking) == tracking
