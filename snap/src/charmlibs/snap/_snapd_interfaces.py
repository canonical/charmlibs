# Copyright 2021 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Snap interface operations, implemented as calls to the snapd API's /v2/interfaces endpoint."""

from __future__ import annotations

import dataclasses
from typing import Any

from . import _client, _errors

# /v2/interfaces


def connect(
    plug_snap: str, plug: str, slot_snap: str | None = None, slot: str | None = None, /
) -> None:
    """Connect a snap and plug, to a target snap and slot."""
    data = {
        'action': 'connect',
        'plugs': [{'snap': plug_snap, 'plug': plug}],
        'slots': [{'snap': slot_snap or '', 'slot': slot or ''}],
    }
    _client.post('/v2/interfaces', body=data)


def disconnect(
    plug_or_slot_snap: str,
    plug_or_slot: str,
    slot_snap: str | None = None,
    slot: str | None = None,
    /,
    *,
    forget: bool = False,
) -> None:
    """Disconnect a plug from a slot."""
    data: dict[str, Any] = {'action': 'disconnect'}
    if slot_snap is None:
        assert slot is None
        # Called with 2 arguments, treat as as snap disconnect <snap>:<slot>
        data['plugs'] = [{'snap': '', 'plug': ''}]
        data['slots'] = [{'snap': plug_or_slot_snap, 'slot': plug_or_slot}]
    else:
        # Called with 3 or 4 arguments, treat as snap disconnect <snap>:<plug> <snap>:<slot>
        data['plugs'] = [{'snap': plug_or_slot_snap, 'plug': plug_or_slot}]
        data['slots'] = [{'snap': slot_snap, 'slot': slot or ''}]
    if forget:
        data['forget'] = True
    # NOTE: Unlike connect, the API raises interfaces-unchanged if already disconnected.
    # We suppress this to make disconnect symmetric with connect (following the snap CLI).
    try:
        _client.post('/v2/interfaces', body=data)
    except _errors._SnapInterfacesUnchangedError:
        pass  # Follow the snap CLI's lead and suppress this error.


def _list_interfaces(
    snap: str | None = None, connected_only: bool = False
) -> list[dict[str, Any]]:
    """List snap interfaces."""
    query = {'select': 'connected' if connected_only else 'all', 'slots': 'true', 'plugs': 'true'}
    interfaces = _client.get('/v2/interfaces', query=query)
    assert isinstance(interfaces, list)
    if snap is None:
        return interfaces
    return [
        i
        for i in interfaces
        if any(p['snap'] == snap for p in i.get('plugs', []))
        or any(s['snap'] == snap for s in i.get('slots', []))
    ]


@dataclasses.dataclass
class _Plug:
    interface: str
    plug: str


def _list_plugs(snap: str, connected_only: bool = False) -> list[_Plug]:  # pyright: ignore[reportUnusedFunction]
    interfaces = _list_interfaces(snap, connected_only=connected_only)
    return [
        _Plug(interface=i['name'], plug=p['plug'])
        for i in interfaces
        for p in i.get('plugs', [])
        if p['snap'] == snap
    ]


@dataclasses.dataclass
class _Slot:
    interface: str
    slot: str


def _list_slots(snap: str, connected_only: bool = False) -> list[_Slot]:  # pyright: ignore[reportUnusedFunction]
    interfaces = _list_interfaces(snap, connected_only=connected_only)
    return [
        _Slot(interface=i['name'], slot=s['slot'])
        for i in interfaces
        for s in i.get('slots', [])
        if s['snap'] == snap
    ]
