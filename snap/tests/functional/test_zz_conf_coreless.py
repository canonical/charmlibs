#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for system configuration on a system without the core snap.

snapd's conf endpoints treat 'system' as an alias for 'core' and serve system configuration
whether or not the core snap is installed, while /v2/snaps/system always 404s and /v2/snaps/core
404s when the core snap is absent. These tests force a core-less system to pin that behaviour --
in particular that get() doesn't probe /v2/snaps/{snap} for these names, which would turn
working system configuration calls into NotFoundError.

Core-less is the norm on current releases (snaps use core NN bases), but snaps that declare no
base (like hello-world, which predates the bases mechanism and is installed by other test
modules) pull in the core snap as a prerequisite -- it doubles as their implicit base.
The module is named test_zz_* so that it runs after the other modules: it removes the core
snap for the whole module (restoring it afterwards),
which could otherwise disturb tests that run while it's gone. Note that removing the core snap
deletes stored system configuration (snapd treats core's config like any other snap's on
removal, though options snapd itself maintains, like seed.loaded, are re-mirrored on the next
snapd restart) -- so tests must not rely on stored system options that they didn't set
themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs import snap
from charmlibs.snap import _errors, _functions, _snapd_conf
from conftest import ensure_removed

if TYPE_CHECKING:
    from collections.abc import Iterator

# A validated system option (documented range 2-20) that is unset by default.
_OPTION = 'refresh.retain'


@pytest.fixture(scope='module', autouse=True)
def without_core_snap() -> Iterator[None]:
    if _functions._get_info('core') is None:
        yield
        return
    # hello-world (no declared base, so core is its base) is installed by other test modules
    # and would block removal.
    ensure_removed('hello-world')
    try:
        snap.remove('core')
    except snap.Error:
        pytest.skip('the core snap is installed and cannot be removed on this system')
    yield
    snap.install('core')


@pytest.mark.parametrize('name', ['system', 'core'])
def test_get_system_conf_without_core_snap(name: str):
    config = _snapd_conf.get(name)
    assert isinstance(config, dict)
    assert 'system' in config  # Computed live by snapd (hostname, timezone, and so on).


def test_get_system_and_core_are_aliases_without_core_snap():
    assert _snapd_conf.get('system') == _snapd_conf.get('core')


@pytest.mark.parametrize('name', ['system', 'core'])
def test_get_system_missing_key_raises_option_not_found(name: str):
    # This is the case a /v2/snaps/{snap} probe in get() would break: the probe 404s while the
    # configuration itself is served, so it must be skipped for the system names.
    with pytest.raises(_errors.OptionNotFoundError) as ctx:
        _snapd_conf.get(name, 'key-that-does-not-exist-xyz')
    assert ctx.value.kind == 'option-not-found'


@pytest.mark.parametrize('name', ['system', 'core'])
def test_set_system_unknown_option_raises_change_error(name: str):
    # System configuration is validated even with no core snap installed: snapd's internal
    # configure handler rejects unknown options and the failed change surfaces as ChangeError.
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_conf.set(name, {'test-unknown-key-xyz': 'value'})
    assert 'unsupported system option' in ctx.value.message


@pytest.mark.parametrize('name', ['system', 'core'])
def test_set_get_unset_system_option_without_core_snap(name: str):
    # set/unset on system configuration are handled internally by snapd (no configure hook),
    # and work whether or not the core snap is installed.
    # No pre-existing value to preserve: if the fixture removed the core snap, stored system
    # configuration was wiped with it, and this module treats stored system options as
    # expendable anyway (see the module docstring).
    try:
        _snapd_conf.set(name, {_OPTION: 3})
        assert _snapd_conf.get(name, _OPTION) == {_OPTION: 3}
    finally:
        _snapd_conf.unset(name, _OPTION)
    with pytest.raises(_errors.OptionNotFoundError):
        _snapd_conf.get(name, _OPTION)


# Runs last within this module: it temporarily installs the core snap, and removing it again
# deletes all stored system configuration, which earlier tests should not be exposed to.
def test_removing_core_snap_deletes_stored_system_config():
    # Stored system options live in snapd state under the snap name 'core'. Removing the core
    # snap deletes them like any other snap's config. Bare get is NOT empty afterwards: options
    # computed live by snapd (system.hostname and so on) remain; only stored options are lost.
    try:
        _snapd_conf.set('system', {_OPTION: 3})
        snap.install('core')
        # Installing the core snap does not disturb stored system configuration.
        assert _snapd_conf.get('system', _OPTION) == {_OPTION: 3}
        snap.remove('core')
        # Removing it deletes stored system configuration...
        with pytest.raises(_errors.OptionNotFoundError):
            _snapd_conf.get('system', _OPTION)
        # ...while computed configuration remains, so bare get is not empty.
        assert 'system' in _snapd_conf.get('system')
    finally:
        # A no-op if the test succeeded (the removal wiped the option); cleans up if it failed.
        _snapd_conf.unset('system', _OPTION)
