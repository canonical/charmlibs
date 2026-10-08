#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _functions: ensure_vitality_hint.

The vitality hint is system configuration, so each test starts and ends with it unset.
"""

import subprocess

import pytest

from charmlibs.snap import _errors, _functions, _snapd_apps, _snapd_conf
from conftest import ensure_installed_local

# A snap name that is never installed. snapd accepts any valid snap name in the vitality hint,
# installed or not, so most tests use this to avoid installing anything.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'
_VITALITY_HINT = 'resilience.vitality-hint'
_SERVICE_SNAP = 'test-service-snap'
_SERVICE_UNIT = f'snap.{_SERVICE_SNAP}.daemon.service'


@pytest.fixture
def unset_vitality_hint():
    _snapd_conf.unset('system', _VITALITY_HINT)
    yield
    _snapd_conf.unset('system', _VITALITY_HINT)


def _vitality_hint() -> str | None:
    try:
        return _snapd_conf.get_one('system', _VITALITY_HINT)
    except _errors.OptionNotFoundError:
        return None


def _systemctl_show(prop: str) -> str:
    cmd = ['systemctl', 'show', '-p', prop, '--value', _SERVICE_UNIT]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_sets_unset_option():
    assert _vitality_hint() is None
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is True
    assert _vitality_hint() == _ABSENT_SNAP


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_replaces_empty_string():
    _snapd_conf.set('system', {_VITALITY_HINT: ''})
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is True
    assert _vitality_hint() == _ABSENT_SNAP


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_appends_after_existing_snaps():
    _snapd_conf.set('system', {_VITALITY_HINT: 'foo,bar'})
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is True
    assert _vitality_hint() == f'foo,bar,{_ABSENT_SNAP}'


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_no_op_if_already_listed():
    _snapd_conf.set('system', {_VITALITY_HINT: f'foo,{_ABSENT_SNAP},bar'})
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is False
    assert _vitality_hint() == f'foo,{_ABSENT_SNAP},bar'


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_snapd_raises():
    # snapd rejects it ('snapd snap vitality cannot be changed'), but only after starting a
    # change, so the library rejects it up front.
    with pytest.raises(ValueError, match='snapd'):
        _functions.ensure_vitality_hint('snapd')
    assert _vitality_hint() is None


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_invalid_snap_name_raises():
    with pytest.raises(_errors.ChangeError, match='invalid snap name'):
        _functions.ensure_vitality_hint('Not-A-Valid-Name')
    assert _vitality_hint() is None


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_more_than_100_snaps_raises():
    _snapd_conf.set('system', {_VITALITY_HINT: ','.join(f'snap{i}' for i in range(100))})
    with pytest.raises(_errors.ChangeError, match='cannot set more than 100 snaps'):
        _functions.ensure_vitality_hint(_ABSENT_SNAP)


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_rewrites_running_service_without_restarting_it():
    # The docstring's claim: the unit gets OOMScoreAdjust=-900+rank straight away, but the
    # running process is left alone, so the caller must restart it for the score to apply.
    ensure_installed_local(_SERVICE_SNAP)
    _snapd_apps.start(_SERVICE_SNAP, enable=True)
    _snapd_conf.set('system', {_VITALITY_HINT: 'foo'})
    pid = _systemctl_show('MainPID')
    assert _systemctl_show('OOMScoreAdjust') == '0'
    did_something = _functions.ensure_vitality_hint(_SERVICE_SNAP)
    assert did_something is True
    assert _systemctl_show('OOMScoreAdjust') == '-898'  # Second in the list.
    assert _systemctl_show('MainPID') == pid
    _snapd_apps.stop(_SERVICE_SNAP, disable=True)
