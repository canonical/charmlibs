#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for system configuration via _snapd_conf: get/set/unset on 'system'.

snapd's conf endpoints treat 'system' as an alias for the 'core' snap and serve system
configuration whether or not the core snap is installed. The `core_snap` fixture runs every
test here in both states -- core installed and core absent -- because the absent state is where
get()'s installed-snap probe must be skipped: /v2/snaps/system always 404s and /v2/snaps/core
404s with no core snap, so probing would turn working calls into _NotFoundError.

This module is destructive to stored system configuration: removing the core snap deletes it
(snapd treats core's config like any other snap's; options snapd maintains itself, such as
seed.loaded, are re-mirrored on the next snapd restart). Tests therefore never preserve
pre-existing system options -- run this only where system configuration is disposable, as in
CI containers.

Ordering: the module needs no special ordering relative to other modules. It removes and
restores the core snap within its own fixture, no other module depends on system configuration,
and any snap a module needs is (re)installed via ensure_installed_store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs import snap
from charmlibs.snap import _errors, _snapd_conf
from conftest import ensure_installed_store, remove_core_blockers

if TYPE_CHECKING:
    from collections.abc import Iterator

# A validated system option (documented range 2-20) that is unset by default.
_OPTION = 'refresh.retain'


@pytest.fixture(scope='module', params=['installed', 'absent'])
def core_snap(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run each test with the core snap installed and again with it absent.

    pytest groups tests by this module-scoped parameter, so the core snap's install state is
    flipped at most once per state, not once per test.

    In the 'absent' state we remove the core snap after removing every snap that is held by
    it (remove_core_blockers asks snapd which those are, so this doesn't need updating when
    another module starts using a new snap). A failed removal is left to error loudly.
    """
    if request.param == 'absent':
        remove_core_blockers()
        snap.remove('core')  # Errors loudly if an unmanaged snap still depends on core.
        yield request.param
        ensure_installed_store('core')
    else:
        ensure_installed_store('core')  # A no-op if already installed.
        yield request.param


@pytest.mark.parametrize('name', ['system', 'core'])
def test_get_system_conf(core_snap: str, name: str):
    config = _snapd_conf.get(name)
    assert isinstance(config, dict)
    assert 'system' in config  # Computed live by snapd (hostname, timezone, and so on).


def test_get_system_and_core_are_aliases(core_snap: str):
    assert _snapd_conf.get('system') == _snapd_conf.get('core')


@pytest.mark.parametrize('name', ['system', 'core'])
def test_get_system_missing_key_raises_option_not_found(core_snap: str, name: str):
    # The case get()'s probe would break: /v2/snaps/{name} 404s while the configuration is
    # served, so the probe must be skipped for these names.
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(name, ['key-that-does-not-exist-xyz'])
    assert ctx.value.kind == 'option-not-found'
    # snapd resolves the alias in the error details: SnapName is always reported as 'core'.
    assert 'core' in str(ctx.value.value)


@pytest.mark.parametrize('name', ['system', 'core'])
def test_set_system_unknown_option_raises_change_error(core_snap: str, name: str):
    # Unlike schemaless snap configuration, system configuration is validated: snapd's internal
    # configure handler rejects unknown options and the failed change surfaces as ChangeError.
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_conf.set(name, {'test-unknown-key-xyz': 'value'})
    assert 'unsupported system option' in ctx.value.message
    # The failed change is rolled back: nothing was stored.
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(name, ['test-unknown-key-xyz'])


@pytest.mark.parametrize('name', ['system', 'core'])
def test_set_get_unset_system_option(core_snap: str, name: str):
    # System set/unset are handled internally by snapd (no configure hook or snap required).
    # This module treats stored system options as expendable, so we don't preserve/restore.
    try:
        _snapd_conf.set(name, {_OPTION: 3})
        assert _snapd_conf.get(name, [_OPTION]) == {_OPTION: 3}
    finally:
        _snapd_conf.unset(name, [_OPTION])
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(name, [_OPTION])


@pytest.mark.parametrize('name', ['system', 'core'])
def test_set_empty_dict_is_noop(core_snap: str, name: str):
    # set(name, {}) sends an empty body, accepted as a no-op that leaves existing configuration
    # untouched (it does NOT unset everything), whether or not the core snap is installed.
    try:
        _snapd_conf.set(name, {_OPTION: 3})
        _snapd_conf.set(name, {})
        assert _snapd_conf.get(name, [_OPTION]) == {_OPTION: 3}
    finally:
        _snapd_conf.unset(name, [_OPTION])


def test_removing_core_snap_deletes_stored_system_config():
    # Stored system options live in snapd state under the snap name 'core'. Removing the core
    # snap deletes them like any other snap's config, while options computed live by snapd
    # (system.hostname and so on) survive. This test manages the core snap itself, so it does
    # not use the core_snap fixture.
    ensure_installed_store(
        'core'
    )  # Ensure installed, so its removal actually deletes stored config.
    _snapd_conf.set('system', {_OPTION: 3})
    assert _snapd_conf.get('system', [_OPTION]) == {_OPTION: 3}
    remove_core_blockers()  # Base-less snaps would otherwise block core removal.
    snap.remove('core')
    try:
        # Removal deleted the stored option...
        with pytest.raises(_errors.OptionNotFoundError):
            _snapd_conf.get('system', [_OPTION])
        # ...while computed configuration remains, so bare get is not empty.
        assert 'system' in _snapd_conf.get('system')
    finally:
        ensure_installed_store('core')  # Restore the core snap for other tests.
        _snapd_conf.unset('system', [_OPTION])  # A no-op if the removal already wiped it.
