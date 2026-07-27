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


class TestEmptySnapName:
    def test_alias_empty_snap_raises_value_error_without_request(self, mock_client: MockClient):
        # snapd would answer with a typed 'snap "" is not installed'; we reject the caller error
        # up front, consistently with the rest of the library.
        with pytest.raises(ValueError, match='must not be empty'):
            _snapd_aliases.alias('', 'lxc', 'testlxc')
        mock_client.post.assert_not_called()
