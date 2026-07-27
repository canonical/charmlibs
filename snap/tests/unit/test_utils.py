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


class TestRaiseIfSnapNameEmpty:
    def test_empty_raises(self):
        with pytest.raises(ValueError, match='must not be empty'):
            _utils.raise_if_snap_name_empty('')

    @pytest.mark.parametrize('snap', ['hello-world', 'lxd', '..', 'a/b', ' '])
    def test_non_empty_does_not_raise(self, snap: str):
        # Only emptiness is checked here -- names that aren't usable in a path are the
        # business of snap_path_segment.
        _utils.raise_if_snap_name_empty(snap)


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
        ('channel', 'current', 'expected'),
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
    def test_resolve(self, channel: str, current: str, expected: str):
        assert _utils.resolve_channel(channel, current) == expected

    @pytest.mark.parametrize('channel', ['stable', 'candidate', 'beta', 'edge'])
    def test_resolving_the_current_channel_is_a_no_op(self, channel: str):
        # ensure() relies on this to tell whether a requested channel is the one already
        # tracked, so resolving a snap's own channel must give that channel back unchanged.
        for track in ('latest', '3.6'):
            current = f'{track}/{channel}'
            assert _utils.resolve_channel(channel, current) == current
            assert _utils.resolve_channel(current, current) == current
