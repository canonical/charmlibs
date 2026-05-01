#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_snaps: info, install, remove, refresh, hold, unhold."""

import datetime

import pytest

from charmlibs.snap import _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed

# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


def test_info_installed():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel
    assert info.revision > 0
    assert info.version


def test_info_missing_ok_false_raises_by_default():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd.info('hello-world')
    assert ctx.value.kind == 'snap-not-found'


def test_info_missing_ok_true_returns_none():
    ensure_removed('hello-world')
    result = _snapd.info('hello-world', missing_ok=True)
    assert result is None


def test_info_fields():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.classic is False
    assert info.hold is None


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def test_install():
    ensure_removed('hello-world')
    _snapd.install('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel == 'latest/stable'


def test_install_already_installed_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAlreadyInstalledError) as ctx:
        _snapd.install('hello-world')
    assert ctx.value.kind == 'snap-already-installed'


def test_install_needs_classic_raises():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.SnapNeedsClassicError) as ctx:
        _snapd.install('charmcraft')
    assert ctx.value.kind == 'snap-needs-classic'


def test_install_classic():
    ensure_removed('charmcraft')
    _snapd.install('charmcraft', classic=True)
    info = _snapd.info('charmcraft')
    assert info.classic is True


def test_install_channel():
    ensure_removed('hello-world')
    _snapd.install('hello-world', channel='latest/candidate')
    info = _snapd.info('hello-world')
    assert info.channel == 'latest/candidate'


def test_install_revision():
    ensure_removed('hello-world')
    # hello-world revision 28 is one behind the current 29.
    _snapd.install('hello-world', revision=28)
    info = _snapd.info('hello-world')
    assert info.revision == 28


def test_install_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.install('hello-world', channel='latest/stable', revision=28)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def test_remove():
    ensure_installed('hello-world')
    _snapd.remove('hello-world')
    assert _snapd.info('hello-world', missing_ok=True) is None


def test_remove_not_installed_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd.remove('hello-world')
    assert ctx.value.kind in ('snap-not-found', 'snap-not-installed')


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


def test_refresh_channel():
    ensure_installed('hello-world', channel='latest/stable')
    _snapd.refresh('hello-world', channel='latest/candidate')
    info = _snapd.info('hello-world')
    assert info.channel == 'latest/candidate'


def test_refresh_no_updates_suppressed():
    # refresh with no available updates should not raise (the error is suppressed).
    ensure_installed('hello-world', channel='latest/stable')
    _snapd.refresh('hello-world', channel='latest/stable')
    # Still installed and unchanged.
    assert _snapd.info('hello-world').channel == 'latest/stable'


def test_refresh_not_installed_raises_base_snap_error():
    # The API returns an error with no 'kind' when refreshing a non-installed snap.
    # This is distinct from SnapNotFoundError; it's a base SnapError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapError) as ctx:
        _snapd.refresh('hello-world')
    # No kind is set -- the message contains "is not installed" but snapd omits the kind field.
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_refresh_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.refresh('hello-world', channel='latest/stable', revision=28)


# ---------------------------------------------------------------------------
# hold / unhold
# ---------------------------------------------------------------------------


def test_hold_with_duration():
    ensure_installed('hello-world')
    _snapd.hold('hello-world', duration=datetime.timedelta(days=2))
    info = _snapd.info('hello-world')
    assert info.hold is not None
    assert info.hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)


def test_hold_forever():
    ensure_installed('hello-world')
    _snapd.hold('hello-world')
    info = _snapd.info('hello-world')
    # When held forever, snapd returns a far-future timestamp.
    assert info.hold is not None


def test_hold_not_installed_raises_base_snap_error():
    # The API returns an error with no 'kind' when holding a non-installed snap.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapError) as ctx:
        _snapd.hold('hello-world')
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_unhold():
    ensure_installed('hello-world')
    _snapd.hold('hello-world')
    assert _snapd.info('hello-world').hold is not None
    _snapd.unhold('hello-world')
    assert _snapd.info('hello-world').hold is None


def test_unhold_not_installed_no_error():
    # unhold on a non-installed snap succeeds silently (async Done).
    ensure_removed('hello-world')
    _snapd.unhold('hello-world')  # should not raise
