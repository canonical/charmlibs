# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

from charmlibs.snap import _snapd_interfaces
from charmlibs.snap._snapd_interfaces import _Plug, _Slot
from conftest import result_of

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

    def test_disconnect_no_forget_default(self, mock_client: MockClient):
        _snapd_interfaces.disconnect('vlc', 'mount-observe')
        body = mock_client.post.call_args.kwargs['body']
        assert 'forget' not in body

    def test_disconnect_action(self, mock_client: MockClient):
        _snapd_interfaces.disconnect('vlc', 'mount-observe')
        body = mock_client.post.call_args.kwargs['body']
        assert body['action'] == 'disconnect'


class TestListInterfaces:
    def test_list_all(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        interfaces = _snapd_interfaces._list_interfaces()
        assert len(interfaces) == 2
        mock_client.get.assert_called_once_with(
            '/v2/interfaces',
            query={'select': 'all', 'slots': 'true', 'plugs': 'true'},
        )

    def test_filter_plug_snap(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        # vlc only has a plug in mount-observe
        interfaces = _snapd_interfaces._list_interfaces(snap='vlc')
        assert len(interfaces) == 1
        assert interfaces[0]['name'] == 'mount-observe'

    def test_filter_slot_snap(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        # snapd has slots in both interfaces
        interfaces = _snapd_interfaces._list_interfaces(snap='snapd')
        assert len(interfaces) == 2

    def test_snap_not_present(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        interfaces = _snapd_interfaces._list_interfaces(snap='unknown')
        assert interfaces == []

    def test_connected_only(self, mock_client: MockClient):
        mock_client.get.return_value = []
        _snapd_interfaces._list_interfaces(connected_only=True)
        query = mock_client.get.call_args.kwargs['query']
        assert query['select'] == 'connected'

    def test_all_not_connected_only(self, mock_client: MockClient):
        mock_client.get.return_value = []
        _snapd_interfaces._list_interfaces(connected_only=False)
        query = mock_client.get.call_args.kwargs['query']
        assert query['select'] == 'all'


class TestListPlugs:
    def test_list_plugs_vlc(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        plugs = _snapd_interfaces._list_plugs('vlc')
        assert len(plugs) == 1
        assert plugs[0] == _Plug(interface='mount-observe', plug='mount-observe')

    def test_list_plugs_lxd(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        plugs = _snapd_interfaces._list_plugs('lxd')
        assert len(plugs) == 1
        assert plugs[0] == _Plug(interface='lxd-support', plug='lxd-support')

    def test_list_plugs_empty(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        plugs = _snapd_interfaces._list_plugs('unknown')
        assert plugs == []


class TestListSlots:
    def test_list_slots_core(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        slots = _snapd_interfaces._list_slots('snapd')
        assert len(slots) == 2
        slot_names = {s.slot for s in slots}
        assert slot_names == {'mount-observe', 'lxd-support'}

    def test_list_slots_empty(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        slots = _snapd_interfaces._list_slots('unknown')
        assert slots == []

    def test_list_slots_returns_slot_dataclass(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('interfaces_all.json')
        slots = _snapd_interfaces._list_slots('snapd')
        assert all(isinstance(s, _Slot) for s in slots)
