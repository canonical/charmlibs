# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from charmlibs.snap import _snapd_apps

if TYPE_CHECKING:
    from conftest import MockClient


class TestStart:
    def test_start_snap_only(self, mock_client: MockClient):
        _snapd_apps.start('lxd')
        mock_client.post.assert_called_once_with(
            '/v2/apps', body={'action': 'start', 'names': ['lxd']}
        )

    def test_start_with_service(self, mock_client: MockClient):
        _snapd_apps.start('lxd', 'daemon')
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon']

    def test_start_multiple_services(self, mock_client: MockClient):
        _snapd_apps.start('lxd', 'daemon', 'user-daemon')
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon', 'lxd.user-daemon']

    def test_start_enable(self, mock_client: MockClient):
        _snapd_apps.start('lxd', enable=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['enable'] is True


class TestStop:
    def test_stop_snap_only(self, mock_client: MockClient):
        _snapd_apps.stop('lxd')
        mock_client.post.assert_called_once_with(
            '/v2/apps', body={'action': 'stop', 'names': ['lxd']}
        )

    def test_stop_with_service(self, mock_client: MockClient):
        _snapd_apps.stop('lxd', 'daemon')
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon']

    def test_stop_disable(self, mock_client: MockClient):
        _snapd_apps.stop('lxd', disable=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['disable'] is True


class TestRestart:
    def test_restart_snap_only(self, mock_client: MockClient):
        _snapd_apps.restart('lxd')
        mock_client.post.assert_called_once_with(
            '/v2/apps', body={'action': 'restart', 'names': ['lxd']}
        )

    def test_restart_with_service(self, mock_client: MockClient):
        _snapd_apps.restart('lxd', 'daemon')
        body = mock_client.post.call_args.kwargs['body']
        assert body['names'] == ['lxd.daemon']


_FUNCTIONS = [_snapd_apps.start, _snapd_apps.stop, _snapd_apps.restart]


class TestEmptySnapName:
    # /v2/apps takes the snap name in the request body, where snapd already answers an empty name
    # with a typed 'snap "" not found'. We still reject it up front, so that every function in the
    # library reports an empty snap name the same way.
    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_name_raises_value_error_without_request(
        self, mock_client: MockClient, func: Any
    ):
        with pytest.raises(ValueError, match='must not be empty'):
            func('')
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('func', _FUNCTIONS, ids=lambda f: f.__name__)
    def test_empty_name_with_services_raises(self, mock_client: MockClient, func: Any):
        with pytest.raises(ValueError, match='must not be empty'):
            func('', 'daemon')
        mock_client.post.assert_not_called()
