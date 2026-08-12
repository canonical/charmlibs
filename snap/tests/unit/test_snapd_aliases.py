# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_aliases

if TYPE_CHECKING:
    from conftest import MockClient


class TestAlias:
    def test_alias(self, mock_client: MockClient):
        _snapd_aliases.alias('lxd', 'lxc', 'testlxc')
        mock_client.post.assert_called_once_with(
            '/v2/aliases',
            body={'action': 'alias', 'snap': 'lxd', 'app': 'lxc', 'alias': 'testlxc'},
        )


class TestUnalias:
    def test_unalias(self, mock_client: MockClient):
        _snapd_aliases.unalias('testlxc')
        mock_client.post.assert_called_once_with(
            '/v2/aliases',
            body={'action': 'unalias', 'alias': 'testlxc'},
        )


class TestEmptyOrBlankFields:
    # snapd reports each of these itself -- a typed 'snap "" is not installed' for the snap, and
    # an APIError or ChangeError naming the offending value for the app and the alias -- but only
    # after a round trip, and for the app only once the change runs. We reject the caller error up
    # front, consistently with the rest of the library.
    @pytest.mark.parametrize('value', ['', ' ', '\t'])
    def test_alias_snap_raises_value_error_without_request(
        self, mock_client: MockClient, value: str
    ):
        with pytest.raises(ValueError, match='snap name must not be'):
            _snapd_aliases.alias(value, 'lxc', 'testlxc')
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('value', ['', ' ', '\t'])
    def test_alias_app_raises_value_error_without_request(
        self, mock_client: MockClient, value: str
    ):
        with pytest.raises(ValueError, match='app name must not be'):
            _snapd_aliases.alias('lxd', value, 'testlxc')
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('value', ['', ' ', '\t'])
    def test_alias_alias_raises_value_error_without_request(
        self, mock_client: MockClient, value: str
    ):
        with pytest.raises(ValueError, match='alias must not be'):
            _snapd_aliases.alias('lxd', 'lxc', value)
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('value', ['', ' ', '\t'])
    def test_unalias_raises_value_error_without_request(self, mock_client: MockClient, value: str):
        with pytest.raises(ValueError, match='alias must not be'):
            _snapd_aliases.unalias(value)
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('value', [' lxd ', 'a,b', 'a b'])
    def test_other_unusable_values_are_left_to_snapd(self, mock_client: MockClient, value: str):
        # These fields go in a JSON body, not a comma-separated query parameter, so snapd sees
        # them exactly as passed and reports them clearly. Only empty and blank are ours to catch.
        _snapd_aliases.alias(value, value, value)
        mock_client.post.assert_called_once_with(
            '/v2/aliases',
            body={'action': 'alias', 'snap': value, 'app': value, 'alias': value},
        )
