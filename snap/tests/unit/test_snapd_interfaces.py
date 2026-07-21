# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_interfaces
from charmlibs.snap._errors import _InterfacesUnchangedError

if TYPE_CHECKING:
    from conftest import MockClient


class TestConnect:
    def test_connect_plug_only_auto_resolves_slot(self, mock_client: MockClient):
        # slot=None -> empty slot snap and name, so snapd auto-resolves the system slot.
        _snapd_interfaces.connect(('vlc', 'mount-observe'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'mount-observe'}]
        assert body['slots'] == [{'snap': '', 'slot': ''}]

    def test_connect_slot_bare_snap_name(self, mock_client: MockClient):
        # A bare snap-name slot means 'resolve the matching slot on this snap'.
        _snapd_interfaces.connect(('vlc', 'mount-observe'), 'core')
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': 'core', 'slot': ''}]

    def test_connect_slot_explicit_pair(self, mock_client: MockClient):
        _snapd_interfaces.connect(('vlc', 'plug'), ('core', 'myslot'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'plug'}]
        assert body['slots'] == [{'snap': 'core', 'slot': 'myslot'}]

    def test_connect_slot_pair_with_empty_name(self, mock_client: MockClient):
        # An explicit pair with an empty slot name is passed through unchanged.
        _snapd_interfaces.connect(('vlc', 'plug'), ('core', ''))
        body = mock_client.post.call_args.kwargs['body']
        assert body['slots'] == [{'snap': 'core', 'slot': ''}]

    def test_connect_action_and_endpoint(self, mock_client: MockClient):
        _snapd_interfaces.connect(('vlc', 'mount-observe'))
        mock_client.post.assert_called_once()
        assert mock_client.post.call_args.args[0] == '/v2/interfaces'
        assert mock_client.post.call_args.kwargs['body']['action'] == 'connect'

    def test_connect_bare_string_plug_raises(self, mock_client: MockClient):
        # A bare snap name is not accepted for the plug: unpacking the 4-char string fails.
        with pytest.raises(ValueError, match='unpack'):
            _snapd_interfaces.connect('vlc')  # pyright: ignore[reportArgumentType]
        mock_client.post.assert_not_called()


class TestDisconnect:
    def test_disconnect_plug_only(self, mock_client: MockClient):
        # Single-sided: plug specified, slot side left empty for snapd to match against.
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'mount-observe'}]
        assert body['slots'] == [{'snap': '', 'slot': ''}]

    def test_disconnect_slot_only(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(slot=('core', 'myslot'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': '', 'plug': ''}]
        assert body['slots'] == [{'snap': 'core', 'slot': 'myslot'}]

    def test_disconnect_both_sides(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'plug'), ('core', 'slot'))
        body = mock_client.post.call_args.kwargs['body']
        assert body['plugs'] == [{'snap': 'vlc', 'plug': 'plug'}]
        assert body['slots'] == [{'snap': 'core', 'slot': 'slot'}]

    def test_disconnect_neither_side_raises(self, mock_client: MockClient):
        with pytest.raises(ValueError, match='at least one'):
            _snapd_interfaces.disconnect()
        mock_client.post.assert_not_called()

    def test_disconnect_forget(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'), forget=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['forget'] is True

    def test_disconnect_no_forget_key_by_default(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))
        assert 'forget' not in mock_client.post.call_args.kwargs['body']

    def test_disconnect_action(self, mock_client: MockClient):
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))
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
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'))  # Should not raise.

    def test_disconnect_interfaces_unchanged_suppressed_with_forget(self, mock_client: MockClient):
        # _InterfacesUnchangedError is suppressed even when forget=True.
        mock_client.post.side_effect = _InterfacesUnchangedError(
            'nothing to do',
            kind='interfaces-unchanged',
            value='',
            status_code=400,
            status='Bad Request',
        )
        _snapd_interfaces.disconnect(('vlc', 'mount-observe'), forget=True)  # Should not raise.
