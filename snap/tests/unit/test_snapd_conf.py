# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_conf
from charmlibs.snap._errors import ChangeError
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


class TestSetAdditional:
    def test_set_empty_dict(self, mock_client: MockClient):
        # set({}) sends an empty body — the API accepts it as a no-op.
        _snapd_conf.set('lxd', {})
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={})


class TestUnsetAdditional:
    def test_unset_dotted_path(self, mock_client: MockClient):
        # unset() with a dotted-path key passes it as-is to the API.
        _snapd_conf.unset('lxd', 'parent.child')
        mock_client.put.assert_called_once_with('/v2/snaps/lxd/conf', body={'parent.child': None})


class TestConfigureHookFailure:
    # Setting or unsetting config runs the snap's configure hook as an async change. A failing
    # hook (including a snap with no configure hook) surfaces as a ChangeError.
    _CHANGE_ERROR = ChangeError(
        'cannot perform the following tasks:\n'
        '- Run configure hook of "hello-world" snap (snap "hello-world" has no "configure" hook)',
        kind='charmlibs-snap-change-error',
        value='63',
        status='Error',
    )

    def test_set_change_error_propagates(self, mock_client: MockClient):
        mock_client.put.side_effect = self._CHANGE_ERROR
        with pytest.raises(ChangeError):
            _snapd_conf.set('hello-world', {'mykey': 'myval'})

    def test_unset_change_error_propagates(self, mock_client: MockClient):
        mock_client.put.side_effect = self._CHANGE_ERROR
        with pytest.raises(ChangeError):
            _snapd_conf.unset('hello-world', 'mykey')
