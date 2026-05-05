# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_conf
from charmlibs.snap._errors import SnapOptionNotFoundError
from conftest import result_of

if TYPE_CHECKING:
    from conftest import MockClient


class TestGet:
    def test_get_all(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        _snapd_conf.get('lxd')
        mock_client.get.assert_called_once_with('/v2/snaps/lxd/conf', query=None)

    def test_get_specific_key(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_single_key.json')
        _snapd_conf.get('lxd', 'integer')
        mock_client.get.assert_called_once_with('/v2/snaps/lxd/conf', query={'keys': 'integer'})

    def test_get_multiple_keys(self, mock_client: MockClient):
        mock_client.get.return_value = {}
        _snapd_conf.get('lxd', 'a', 'b')
        query = mock_client.get.call_args.kwargs['query']
        assert query == {'keys': 'a,b'}

    def test_get_returns_dict(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('conf_lxd_all.json')
        result = _snapd_conf.get('lxd')
        assert isinstance(result, dict)
        assert 'criu' in result


class TestGetOne:
    def test_get_one(self, mock_client: MockClient):
        mock_client.get.return_value = {'core.https_address': '[::]:8443'}
        result = _snapd_conf._get_one('lxd', 'core.https_address')
        assert result == '[::]:8443'

    def test_get_one_missing(self, mock_client: MockClient):
        mock_client.get.side_effect = SnapOptionNotFoundError(
            'snap "lxd" has no "keydoesnotexist01" configuration option',
            kind='option-not-found',
            value='',
            status_code=400,
            status='Bad Request',
        )
        with pytest.raises(SnapOptionNotFoundError):
            _snapd_conf._get_one('lxd', 'keydoesnotexist01')


class TestSet:
    def test_set(self, mock_client: MockClient):
        _snapd_conf.set('lxd', {'mykey': 'myval'})
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'mykey': 'myval'})


class TestUnset:
    def test_unset_single(self, mock_client: MockClient):
        _snapd_conf.unset('lxd', 'mykey')
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'mykey': None})

    def test_unset_multiple(self, mock_client: MockClient):
        _snapd_conf.unset('lxd', 'a', 'b')
        body = mock_client.put.call_args.kwargs['body']
        assert body == {'a': None, 'b': None}
