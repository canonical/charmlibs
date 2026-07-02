#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_interfaces: connect, disconnect."""

from __future__ import annotations

import dataclasses
import typing
from typing import Any

import pytest

from charmlibs.snap import _client, _errors, _snapd_interfaces
from conftest import ensure_installed

_SNAP = 'htop'
_PLUG = 'mount-observe'
# snapd auto-resolves the mount-observe slot to snapd.
_SLOT_SNAP = 'snapd'
_SLOT = 'mount-observe'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# Test helpers and possible future candidates for library public API.
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Plug:
    interface: str
    plug: str


@dataclasses.dataclass
class _Slot:
    interface: str
    slot: str


def _list_plugs(snap: str, connected_only: bool = False) -> list[_Plug]:
    interfaces = _list_interfaces(snap, connected_only=connected_only)
    return [
        _Plug(interface=i['name'], plug=p['plug'])
        for i in interfaces
        for p in i.get('plugs', [])
        if p['snap'] == snap
    ]


def _list_slots(snap: str, connected_only: bool = False) -> list[_Slot]:
    interfaces = _list_interfaces(snap, connected_only=connected_only)
    return [
        _Slot(interface=i['name'], slot=s['slot'])
        for i in interfaces
        for s in i.get('slots', [])
        if s['snap'] == snap
    ]


def _list_interfaces(
    snap: str | None = None, connected_only: bool = False
) -> list[dict[str, Any]]:
    """List snap interfaces."""
    query = {'select': 'connected' if connected_only else 'all', 'slots': 'true', 'plugs': 'true'}
    interfaces = _client.get('/v2/interfaces', query=query)
    assert isinstance(interfaces, list)
    interfaces = typing.cast('list[dict[str, Any]]', interfaces)
    if snap is None:
        return interfaces
    return [
        i
        for i in interfaces
        if any(p['snap'] == snap for p in i.get('plugs', []))
        or any(s['snap'] == snap for s in i.get('slots', []))
    ]


# ---------------------------------------------------------------------------


def _is_connected() -> bool:
    return any(p.plug == _PLUG for p in _list_plugs(_SNAP, connected_only=True))


def _ensure_disconnected() -> None:
    try:
        _snapd_interfaces.disconnect(_SNAP, _PLUG)
    except Exception:  # noqa: S110
        pass
    # Post-condition: the plug really is no longer connected.
    assert not any(p.plug == _PLUG for p in _list_plugs(_SNAP, connected_only=True))


def _ensure_connected() -> None:
    # Pre-condition: the slot side (snapd) actually provides the mount-observe slot,
    # otherwise the connection could never succeed.
    assert any(s.slot == _SLOT for s in _list_slots(_SLOT_SNAP))
    if not _is_connected():
        _snapd_interfaces.connect(_SNAP, _PLUG)
    # Post-condition: the plug is now connected.
    assert _is_connected()


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


def test_connect():
    ensure_installed(_SNAP)
    _ensure_disconnected()
    assert not _is_connected()
    _snapd_interfaces.connect(_SNAP, _PLUG)
    assert _is_connected()


def test_connect_already_connected_no_error():
    # Connecting an already-connected plug should not raise.
    ensure_installed(_SNAP)
    _ensure_connected()
    assert _is_connected()
    _snapd_interfaces.connect(_SNAP, _PLUG)  # Should not raise.
    assert _is_connected()


def test_connect_nonexistent_plug_raises():
    # Connecting a nonexistent plug raises a base Error (no kind from snapd).
    ensure_installed(_SNAP)
    with pytest.raises(_errors.Error) as ctx:
        _snapd_interfaces.connect(_SNAP, 'nonexistent-plug')
    assert not ctx.value.kind
    assert 'nonexistent-plug' in ctx.value.message


def test_connect_with_explicit_slot():
    # connect() accepts an explicit slot snap and slot name.
    ensure_installed(_SNAP)
    _ensure_disconnected()
    _snapd_interfaces.connect(_SNAP, _PLUG, _SLOT_SNAP, _SLOT)
    assert _is_connected()


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


def test_disconnect():
    ensure_installed(_SNAP)
    _ensure_connected()
    assert _is_connected()
    _snapd_interfaces.disconnect(_SNAP, _PLUG)
    assert not _is_connected()


def test_disconnect_not_connected_no_error():
    # Disconnecting a plug that is not connected is a no-op (interfaces-unchanged suppressed).
    # This makes disconnect symmetric with connect: both succeed silently when no change needed.
    ensure_installed(_SNAP)
    _ensure_disconnected()
    _snapd_interfaces.disconnect(_SNAP, _PLUG)  # Should not raise.
    assert not _is_connected()


def test_disconnect_forget_connected_no_error():
    # disconnect forget=True on a connected interface works without error.
    ensure_installed(_SNAP)
    _ensure_connected()
    _snapd_interfaces.disconnect(_SNAP, _PLUG, forget=True)  # Should not raise.


def test_disconnect_forget_not_connected_no_error():
    # disconnect forget=True on a not-connected interface is a no-op
    # (interfaces-unchanged suppressed, same as without forget=True).
    ensure_installed(_SNAP)
    _ensure_disconnected()
    _snapd_interfaces.disconnect(_SNAP, _PLUG, forget=True)  # Should not raise.


def test_disconnect_nonexistent_plug_or_slot_raises():
    # disconnect: plug/slot name doesn't exist on the installed snap.
    ensure_installed(_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.disconnect(_SNAP, 'nonexistent-slot')
    assert not ctx.value.kind
    assert 'no plug or slot named' in ctx.value.message


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_connect_not_installed_snap_raises():
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.connect(_ABSENT_SNAP, 'home')
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_disconnect_not_installed_snap_raises():
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.disconnect(_ABSENT_SNAP, 'home')
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_connect_slot_snap_not_installed_raises():
    # connect: slot snap not installed raises APIError with empty kind.
    ensure_installed(_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.connect(_SNAP, _PLUG, _ABSENT_SNAP, _SLOT)
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message
