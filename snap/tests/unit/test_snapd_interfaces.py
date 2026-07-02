# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

from charmlibs.snap import _snapd_interfaces
from charmlibs.snap._errors import _InterfacesUnchangedError

if TYPE_CHECKING:
    from conftest import MockClient


class TestConnect:
    def test_connect_plug_only(self, mock_client: MockClient):
        _snapd_interfaces.connect('vlc', 'mount-observe')
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': '', 'slot': ''}]

    def test_connect_with_slot_snap_and_slot(self, mock_client: MockClient):
        _snapd_interfaces.connect('vlc', 'plug', 'core', 'myslot')
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': 'core', 'slot': 'myslot'}]
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'plug'}]

    def test_connect_slot_snap_no_slot(self, mock_client: MockClient):
        _snapd_interfaces.connect('vlc', 'plug', 'core')
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': 'core', 'slot': ''}]

    def test_connect_action(self, mock_client: MockClient):
        _snapd_interfaces.connect('vlc', 'mount-observe')
        body = mock_client.post.call_args.kwargs['body']
        assert body['action'] == 'connect'

    def test_connect_endpoint(self, mock_client: MockClient):
        _snapd_interfaces.connect('vlc', 'mount-observe')
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args.args[0] == '/v2/interfaces'


class TestDisconnect:
    def test_disconnect_2_arg(self, mock_client: MockClient):
        _snapd_interfaces.disconnect('vlc', 'mount-observe')
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': '', 'plug': ''}]
        assert body['slots'] == [{'snap': 'vlc', 'slot': 'mount-observe'}]

    def test_disconnect_4_arg(self, mock_client: MockClient):
        _snapd_interfaces.disconnect('vlc', 'plug', 'core', 'slot')
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'plug'}]
        assert body['slots'] == [{'snap': 'core', 'slot': 'slot'}]

    def test_disconnect_3_arg(self, mock_client: MockClient):
        _snapd_interfaces.disconnect('vlc', 'plug', 'core')
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': 'core', 'slot': ''}]

    def test_disconnect_forget(self, mock_client: MockClient):
        _snapd_interfaces.disconnect('vlc', 'mount-observe', forget=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['forget'] is True

    def test_disconnect_action(self, mock_client: MockClient):
        _snapd_interfaces.disconnect('vlc', 'mount-observe')
        body = mock_client.post.call_args.kwargs['body']
        assert body['action'] == 'disconnect'

    def test_disconnect_interfaces_unchanged_suppressed(self, mock_client: MockClient):
        # The try/except in disconnect() suppresses _InterfacesUnchangedError
        # to make disconnect symmetric with connect (both are no-ops when nothing changes).
        mock_client.post.side_effect = _InterfacesUnchangedError(
            'nothing to do',
            kind='interfaces-unchanged',
            value='',
            status_code=400,
            status='Bad Request',
        )
        _snapd_interfaces.disconnect('vlc', 'mount-observe')  # Should not raise.

    def test_disconnect_interfaces_unchanged_suppressed_with_forget(self, mock_client: MockClient):
        # _InterfacesUnchangedError is suppressed even when forget=True.
        mock_client.post.side_effect = _InterfacesUnchangedError(
            'nothing to do',
            kind='interfaces-unchanged',
            value='',
            status_code=400,
            status='Bad Request',
        )
        _snapd_interfaces.disconnect('vlc', 'mount-observe', forget=True)  # Should not raise.
