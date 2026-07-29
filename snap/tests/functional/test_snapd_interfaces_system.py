#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for connect/disconnect against the system snap, core present and absent.

snapd's ``CoreSnapdSystemMapper.RemapSnapFromRequest`` renames ``'core'`` and ``'system'`` to
``'snapd'`` at request time (overlord/ifacestate/helpers.go), before the daemon's installed-snap
check, and the snapd snap hosts the implicit system slots. So connect/disconnect targeting the
system snap -- by auto-resolution (``None``), or explicitly as ``'snapd'``, ``'core'``, or
``'system'`` -- works whether or not the core snap is installed.

Unlike conf, the interfaces library needs no special-casing for this: it performs no installed
checks of its own, and snapd's request-time remap resolves the alias to the always-present snapd
snap. The ``core_snap`` fixture runs every test in both states -- core installed and core absent
-- to prove the core-absent case really is served rather than only appearing to work because core
happened to be present.

Destructive: removes and reinstalls the core snap within its own fixture. Run only where the core
snap is disposable, as in CI containers. The test snap declares ``base: core24`` so it survives
core removal.
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any

import pytest

from charmlibs import snap
from charmlibs.snap import _client, _errors, _snapd_interfaces
from conftest import (
    SNAPS_DIR,
    ensure_installed,
    ensure_removed,
    install_local,
    remove_core_blockers,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

# The local test snap (base: core24, so independent of the core snap) and one of its plugs.
_SNAP = 'test-interfaces-snap'
_PLUG = 'mount-observe'
# The system-snap names snapd accepts for the slot side. 'core' and 'system' are remapped to
# 'snapd' at request time, so all three resolve to the same implicit slots.
_SYSTEM_NAMES = ['snapd', 'core', 'system']


@pytest.fixture(scope='module', autouse=True)
def interfaces_snap() -> Iterator[None]:
    """Sideload the local test snap once for the module, and remove it afterwards."""
    install_local(SNAPS_DIR / f'{_SNAP}_1.0.snap', dangerous=True)
    yield
    ensure_removed(_SNAP)


@pytest.fixture(scope='module', params=['installed', 'absent'])
def core_snap(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run each test with the core snap installed and again with it absent.

    pytest groups tests by this module-scoped parameter, so the core snap's install state is
    flipped at most once per state, not once per test. In the 'absent' state we first remove
    every snap held by core, which would otherwise block its removal; a failed removal is
    left to error loudly, matching test_snapd_conf_system.
    """
    if request.param == 'absent':
        remove_core_blockers()
        snap.remove('core')  # Errors loudly if an unmanaged snap still depends on core.
        yield request.param
        ensure_installed('core')
    else:
        ensure_installed('core')  # A no-op if already installed.
        yield request.param


def _is_connected() -> bool:
    query = {'select': 'connected', 'plugs': 'true', 'slots': 'true'}
    interfaces = _client.get('/v2/interfaces', query=query)
    assert isinstance(interfaces, list)
    interfaces = typing.cast('list[dict[str, Any]]', interfaces)
    return any(
        p['plug'] == _PLUG for i in interfaces for p in i.get('plugs', []) if p['snap'] == _SNAP
    )


def _ensure_disconnected() -> None:
    _snapd_interfaces.disconnect((_SNAP, _PLUG))  # Single-sided: no-op if not connected.
    assert not _is_connected()


def test_core_snap_state_matches_fixture(core_snap: str):
    # Guard: prove the 'absent' parametrisation really removes core, so the tests below are
    # exercising the core-absent path rather than silently running with core present.
    try:
        _client.get('/v2/snaps/core')
        core_installed = True
    except _errors.NotFoundError:
        core_installed = False
    assert core_installed == (core_snap == 'installed')


@pytest.mark.parametrize('slot', [None, *_SYSTEM_NAMES])
def test_connect_system_slot_bare(core_snap: str, slot: str | None):
    # Connect to the system slot by auto-resolution (None) or a bare system-snap name.
    _ensure_disconnected()
    _snapd_interfaces.connect((_SNAP, _PLUG), slot)
    assert _is_connected()
    _ensure_disconnected()


@pytest.mark.parametrize('slot_snap', _SYSTEM_NAMES)
def test_connect_system_slot_explicit_pair(core_snap: str, slot_snap: str):
    # Connect to the system slot named explicitly as (system_snap, mount-observe).
    _ensure_disconnected()
    _snapd_interfaces.connect((_SNAP, _PLUG), (slot_snap, _PLUG))
    assert _is_connected()
    _ensure_disconnected()


@pytest.mark.parametrize('slot_snap', _SYSTEM_NAMES)
def test_disconnect_system_slot(core_snap: str, slot_snap: str):
    # Connect (auto), then disconnect by naming the system slot. 'core'/'system' remap to 'snapd',
    # matching the auto-resolved connection, so the disconnect succeeds in every core state.
    _ensure_disconnected()
    _snapd_interfaces.connect((_SNAP, _PLUG))
    assert _is_connected()
    _snapd_interfaces.disconnect(slot=(slot_snap, _PLUG))
    assert not _is_connected()
