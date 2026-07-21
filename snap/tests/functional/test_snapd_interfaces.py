#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_interfaces: connect, disconnect.

These tests use a local, sideloaded snap (``test-interfaces-snap``, built from
tests/functional/snaps) that declares the ``mount-observe`` and ``system-observe`` plugs.
Both interfaces have a slot on the system snap (``snapd``/``core``), so the plugs can be
connected and disconnected without depending on any snap from the store.
"""

from __future__ import annotations

import typing
from typing import Any

import pytest

from charmlibs.snap import _client, _errors, _snapd_interfaces
from conftest import ensure_removed
from test_snapd_local import SNAPS_DIR, install_local

# The local test snap and one of the plugs it declares. snapd auto-resolves the
# mount-observe slot to the system snap.
_SNAP = 'test-interfaces-snap'
_PLUG = 'mount-observe'
# The system snap that provides the auto-resolved slots. Present on any snapd system.
_SYSTEM_SNAP = 'snapd'

# Snap names that are never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
# Two distinct names are needed to test which snap snapd blames when both are absent.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'
_ABSENT_SNAP_2 = 'this-snap-also-does-not-exist-def-456'


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module', autouse=True)
def interfaces_snap() -> typing.Iterator[None]:
    """Sideload the local test snap once for the module, and remove it afterwards."""
    install_local(SNAPS_DIR / f'{_SNAP}_1.0.snap', dangerous=True)
    yield
    ensure_removed(_SNAP)


def _connected_plugs() -> list[str]:
    """Return the names of currently-connected plugs on the test snap.

    Uses ``select=connected``, under which snapd only lists plugs that are connected, so a
    plug's presence is the signal (the per-plug ``connections`` field is not populated here).
    """
    query = {'select': 'connected', 'plugs': 'true', 'slots': 'true'}
    interfaces = _client.get('/v2/interfaces', query=query)
    assert isinstance(interfaces, list)
    interfaces = typing.cast('list[dict[str, Any]]', interfaces)
    return [p['plug'] for i in interfaces for p in i.get('plugs', []) if p['snap'] == _SNAP]


def _is_connected(plug: str = _PLUG) -> bool:
    return plug in _connected_plugs()


def _ensure_disconnected(plug: str = _PLUG) -> None:
    try:
        _snapd_interfaces.disconnect((_SNAP, plug))
    except Exception:  # noqa: S110
        pass
    assert not _is_connected(plug)


def _ensure_connected(plug: str = _PLUG) -> None:
    if not _is_connected(plug):
        _snapd_interfaces.connect((_SNAP, plug))
    assert _is_connected(plug)


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


def test_connect():
    _ensure_disconnected()
    assert not _is_connected()
    _snapd_interfaces.connect((_SNAP, _PLUG))
    assert _is_connected()


def test_connect_already_connected_no_error():
    # Connecting an already-connected plug should not raise.
    _ensure_connected()
    _snapd_interfaces.connect((_SNAP, _PLUG))  # Should not raise.
    assert _is_connected()


def test_connect_slot_bare_snap_name():
    # A bare snap-name slot auto-resolves the matching slot on that snap.
    _ensure_disconnected()
    _snapd_interfaces.connect((_SNAP, _PLUG), _SYSTEM_SNAP)
    assert _is_connected()


def test_connect_explicit_slot_pair():
    # connect() accepts an explicit (slot_snap, slot) pair.
    _ensure_disconnected()
    _snapd_interfaces.connect((_SNAP, _PLUG), (_SYSTEM_SNAP, _PLUG))
    assert _is_connected()


def test_connect_nonexistent_plug_raises():
    # Connecting a nonexistent plug raises a base Error (no kind from snapd).
    with pytest.raises(_errors.Error) as ctx:
        _snapd_interfaces.connect((_SNAP, 'nonexistent-plug'))
    assert not ctx.value.kind
    assert 'nonexistent-plug' in ctx.value.message


def test_connect_interface_mismatch_raises():
    # Connecting a plug to a slot of a different interface raises APIError (empty kind).
    _ensure_disconnected()
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.connect((_SNAP, _PLUG), (_SYSTEM_SNAP, 'network'))
    assert not ctx.value.kind
    assert 'cannot connect' in ctx.value.message


def test_connect_all_empty_raises():
    # An all-empty connect (empty plug, no slot) flows through to snapd, which rejects it with
    # an empty-kind APIError. We deliberately do not guard this client-side.
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.connect(('', ''), ('', ''))
    assert not ctx.value.kind
    assert 'plug snap name is empty' in ctx.value.message


def test_connect_empty_plug_name_raises():
    # A plug with a snap but no plug name is rejected with a distinct message (the plug snap
    # exists, but snapd cannot resolve which plug to connect).
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.connect((_SNAP, ''))
    assert not ctx.value.kind
    assert 'plug name is empty' in ctx.value.message


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


def test_disconnect_plug_only():
    _ensure_connected()
    _snapd_interfaces.disconnect((_SNAP, _PLUG))
    assert not _is_connected()


def test_disconnect_slot_only():
    # Disconnecting by slot removes everything connected to that slot, including our plug.
    _ensure_connected()
    _snapd_interfaces.disconnect(slot=(_SYSTEM_SNAP, _PLUG))
    assert not _is_connected()


def test_disconnect_both_sides():
    _ensure_connected()
    _snapd_interfaces.disconnect((_SNAP, _PLUG), (_SYSTEM_SNAP, _PLUG))
    assert not _is_connected()


def test_disconnect_plug_only_not_connected_no_error():
    # Single-sided disconnect of a plug that is not connected is a no-op
    # (interfaces-unchanged suppressed). This mirrors connect: both succeed silently.
    _ensure_disconnected()
    _snapd_interfaces.disconnect((_SNAP, _PLUG))  # Should not raise.
    assert not _is_connected()


def test_disconnect_slot_only_not_connected_no_error():
    _ensure_disconnected()
    _snapd_interfaces.disconnect(slot=(_SYSTEM_SNAP, _PLUG))  # Should not raise.


def test_disconnect_both_sides_not_connected_raises():
    # KEY asymmetry: unlike the single-sided forms, a fully-specified disconnect of a plug and
    # slot that are NOT connected raises (snapd returns 'it is not connected', not
    # interfaces-unchanged, so it is not suppressed).
    _ensure_disconnected()
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.disconnect((_SNAP, _PLUG), (_SYSTEM_SNAP, _PLUG))
    assert not ctx.value.kind
    assert 'not connected' in ctx.value.message


def test_disconnect_forget_connected_no_error():
    # disconnect forget=True on a connected interface works without error.
    _ensure_connected()
    _snapd_interfaces.disconnect((_SNAP, _PLUG), forget=True)  # Should not raise.
    assert not _is_connected()


def test_disconnect_forget_not_connected_no_error():
    # disconnect forget=True single-sided on a not-connected interface is a no-op
    # (interfaces-unchanged suppressed, same as without forget=True).
    _ensure_disconnected()
    _snapd_interfaces.disconnect((_SNAP, _PLUG), forget=True)  # Should not raise.


def test_disconnect_both_sides_forget_not_connected_raises():
    # forget=True fully-specified on a not-connected interface raises 'it was not connected'.
    _ensure_disconnected()
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.disconnect((_SNAP, _PLUG), (_SYSTEM_SNAP, _PLUG), forget=True)
    assert not ctx.value.kind
    assert 'not connected' in ctx.value.message


def test_disconnect_nonexistent_plug_or_slot_raises():
    # disconnect: plug/slot name doesn't exist on the installed snap.
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_interfaces.disconnect((_SNAP, 'nonexistent-slot'))
    assert not ctx.value.kind
    assert 'no plug or slot named' in ctx.value.message


def test_disconnect_all_empty_raises():
    # An all-empty disconnect -- whether from no arguments or explicit empty pairs (which encode
    # identically) -- flows through to snapd, which rejects it with an empty-kind APIError. This
    # matches connect's all-empty behaviour; we deliberately do not guard it client-side.
    for args in [(), (('', ''),), (('', ''), ('', ''))]:
        with pytest.raises(_errors.APIError) as ctx:
            _snapd_interfaces.disconnect(*args)
        assert not ctx.value.kind
        assert 'allowed forms are' in ctx.value.message


# ---------------------------------------------------------------------------
# not-installed snap -> typed NotFoundError (uses a never-installed name to avoid churn)
#
# snapd reports a not-installed snap as an empty-kind APIError ('snap "X" is not installed').
# connect/disconnect probe the named snaps on error and re-raise as a typed NotFoundError
# (kind 'snap-not-found'), so callers can catch the type instead of matching the message.
# ---------------------------------------------------------------------------


# The probe hits /v2/snaps/{name}, whose not-found error carries a generic message
# ('snap not installed') and puts the snap name in `value` (unlike the /v2/interfaces message).


def test_connect_not_installed_snap_raises_not_found():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_interfaces.connect((_ABSENT_SNAP, 'home'))
    assert ctx.value.kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value.value)


def test_disconnect_not_installed_snap_raises_not_found():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_interfaces.disconnect((_ABSENT_SNAP, 'home'))
    assert ctx.value.kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value.value)


def test_connect_slot_snap_not_installed_raises_not_found():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_interfaces.connect((_SNAP, _PLUG), (_ABSENT_SNAP, _PLUG))
    assert ctx.value.kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value.value)


# ---------------------------------------------------------------------------
# error ordering
#
# snapd validates a request in a fixed order (daemon/api_interfaces.go): (1) plug snap installed,
# (2) slot snap installed, (3) plug/slot exist and interfaces match. The raw-API tests pin that
# native order (a not-installed snap is an empty-kind APIError, reported before a bad plug name,
# and the plug snap is checked before the slot snap). The library tests then show connect and
# disconnect convert the not-installed case into a typed NotFoundError WITHOUT inverting the order
# -- probing plug-snap before slot-snap names the same snap snapd blames, and callers no longer
# see the yucky empty-kind 'is not installed' error.
# ---------------------------------------------------------------------------


def _raw_connect(plug_snap: str, plug: str, slot_snap: str, slot: str) -> None:
    # POST directly to the API, bypassing the library's not-installed probe, to observe snapd's
    # native error and ordering.
    _client.post(
        '/v2/interfaces',
        body={
            'action': 'connect',
            'plugs': [{'snap': plug_snap, 'plug': plug}],
            'slots': [{'snap': slot_snap, 'slot': slot}],
        },
    )


def test_raw_api_slot_not_installed_precedes_bad_plug():
    # Native snapd: the slot-snap installed-check runs before ResolveConnect, so a not-installed
    # slot snap is reported even with a bad plug name -- as the empty-kind error the library hides.
    with pytest.raises(_errors.APIError) as ctx:
        _raw_connect(_SNAP, 'nonexistent-plug', _ABSENT_SNAP, '')
    assert ctx.value.kind == ''
    assert _ABSENT_SNAP in ctx.value.message
    assert 'is not installed' in ctx.value.message
    assert 'nonexistent-plug' not in ctx.value.message


def test_raw_api_plug_snap_checked_before_slot_snap():
    # Native snapd: when both snaps are absent, the plug snap is reported first.
    with pytest.raises(_errors.APIError) as ctx:
        _raw_connect(_ABSENT_SNAP, 'x', _ABSENT_SNAP_2, '')
    assert ctx.value.kind == ''
    assert _ABSENT_SNAP in ctx.value.message
    assert _ABSENT_SNAP_2 not in ctx.value.message


def test_connect_slot_snap_not_installed_precedes_bad_plug():
    # Library: the not-installed slot snap wins over the bad plug, surfaced as NotFoundError.
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_interfaces.connect((_SNAP, 'nonexistent-plug'), (_ABSENT_SNAP, ''))
    assert ctx.value.kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value.value)
    assert 'nonexistent-plug' not in str(ctx.value.value)


def test_connect_plug_snap_checked_before_slot_snap():
    # Library: both absent -> the plug snap is probed first, so it is the one named.
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_interfaces.connect((_ABSENT_SNAP, 'x'), (_ABSENT_SNAP_2, ''))
    assert ctx.value.kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value.value)
    assert _ABSENT_SNAP_2 not in str(ctx.value.value)


def test_disconnect_slot_snap_not_installed_precedes_bad_plug():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_interfaces.disconnect((_SNAP, 'nonexistent-plug'), (_ABSENT_SNAP, 'x'))
    assert ctx.value.kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value.value)
    assert 'nonexistent-plug' not in str(ctx.value.value)


def test_disconnect_plug_snap_checked_before_slot_snap():
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_interfaces.disconnect((_ABSENT_SNAP, 'x'), (_ABSENT_SNAP_2, 'y'))
    assert ctx.value.kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value.value)
    assert _ABSENT_SNAP_2 not in str(ctx.value.value)
