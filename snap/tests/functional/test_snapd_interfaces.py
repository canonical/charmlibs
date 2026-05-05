#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_interfaces: connect, disconnect."""

import pytest

from charmlibs.snap import _errors, _snapd_interfaces
from conftest import ensure_installed

_SNAP = 'vlc'
_PLUG = 'mount-observe'
# snapd auto-resolves the mount-observe slot to snapd.
_SLOT_SNAP = 'snapd'
_SLOT = 'mount-observe'


def _is_connected() -> bool:
    interfaces = _snapd_interfaces._list_interfaces(_SNAP, connected_only=True)
    return any(
        i['name'] == _PLUG and any(p['snap'] == _SNAP for p in i.get('plugs', []))
        for i in interfaces
    )


def _ensure_disconnected() -> None:
    try:
        _snapd_interfaces.disconnect(_SNAP, _PLUG)
    except Exception:  # noqa: S110
        pass


def _ensure_connected() -> None:
    if not _is_connected():
        _snapd_interfaces.connect(_SNAP, _PLUG)


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
    _snapd_interfaces.connect(_SNAP, _PLUG)  # should not raise
    assert _is_connected()


def test_connect_nonexistent_plug_raises():
    # Connecting a nonexistent plug raises a base SnapError (no kind from snapd).
    ensure_installed(_SNAP)
    with pytest.raises(_errors.SnapError) as ctx:
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
    _snapd_interfaces.disconnect(_SNAP, _PLUG)  # should not raise
    assert not _is_connected()


# ---------------------------------------------------------------------------
# _list_interfaces / _list_plugs / _list_slots
# ---------------------------------------------------------------------------


def test_list_interfaces_returns_list():
    ensure_installed(_SNAP)
    interfaces = _snapd_interfaces._list_interfaces()
    assert isinstance(interfaces, list)
    assert len(interfaces) > 0


def test_list_interfaces_filter_by_snap():
    ensure_installed(_SNAP)
    interfaces = _snapd_interfaces._list_interfaces(_SNAP)
    assert isinstance(interfaces, list)
    # Every returned interface should involve the snap.
    for iface in interfaces:
        snaps_in_iface = {p['snap'] for p in iface.get('plugs', [])} | {
            s['snap'] for s in iface.get('slots', [])
        }
        assert _SNAP in snaps_in_iface


def test_list_interfaces_connected_only():
    ensure_installed(_SNAP)
    _ensure_connected()
    connected = _snapd_interfaces._list_interfaces(_SNAP, connected_only=True)
    assert any(
        i['name'] == _PLUG and any(p['snap'] == _SNAP for p in i.get('plugs', []))
        for i in connected
    )


def test_list_plugs_returns_plugs():
    ensure_installed(_SNAP)
    plugs = _snapd_interfaces._list_plugs(_SNAP)
    assert isinstance(plugs, list)
    plug_names = [p.plug for p in plugs]
    assert _PLUG in plug_names


def test_list_plugs_connected_only():
    ensure_installed(_SNAP)
    _ensure_connected()
    connected_plugs = _snapd_interfaces._list_plugs(_SNAP, connected_only=True)
    assert any(p.plug == _PLUG for p in connected_plugs)
    _ensure_disconnected()
    disconnected_plugs = _snapd_interfaces._list_plugs(_SNAP, connected_only=True)
    assert not any(p.plug == _PLUG for p in disconnected_plugs)
