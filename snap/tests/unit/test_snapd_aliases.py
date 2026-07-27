# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

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
