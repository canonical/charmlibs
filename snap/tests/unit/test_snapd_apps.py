# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from typing import TYPE_CHECKING

from charmlibs.snap import _snapd_apps
from conftest import result_of

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

    def test_start_no_enable_default(self, mock_client: MockClient):
        _snapd_apps.start('lxd')
        body = mock_client.post.call_args.kwargs['body']
        assert 'enable' not in body


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

    def test_stop_no_disable_default(self, mock_client: MockClient):
        _snapd_apps.stop('lxd')
        body = mock_client.post.call_args.kwargs['body']
        assert 'disable' not in body


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


class TestListServices:
    def test_list_services_for_snap(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('services_lxd.json')
        services = _snapd_apps._list_services('lxd')
        assert isinstance(services, list)
        assert len(services) == 3
        assert services[0]['name'] == 'activate'
        mock_client.get.assert_called_once_with(
            '/v2/apps', query={'select': 'service', 'names': 'lxd'}
        )

    def test_list_services_no_snap(self, mock_client: MockClient):
        mock_client.get.return_value = []
        _snapd_apps._list_services()
        query = mock_client.get.call_args.kwargs['query']
        assert 'names' not in query

    def test_list_services_returns_list(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('services_lxd.json')
        result = _snapd_apps._list_services('lxd')
        assert isinstance(result, list)
