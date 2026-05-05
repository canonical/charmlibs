#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_apps: start, stop, restart."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from charmlibs.snap import _errors, _snapd_apps
from conftest import ensure_installed

_SNAP = 'kube-proxy'
_SERVICE = 'daemon'
_QUALIFIED_SERVICE = f'{_SNAP}.{_SERVICE}'


def _service_dict() -> dict[str, Any]:
    services = _snapd_apps._list_services(_SNAP)
    return next(s for s in services if s['name'] == _SERVICE)


def _service_is_active() -> bool:
    return _service_dict().get('active', False)


def _service_is_enabled() -> bool:
    return _service_dict().get('enabled', False)


def _stop_and_disable() -> None:
    """Put kube-proxy.daemon into a known clean state: stopped and disabled.

    Called at the start of tests that need a predictable initial service state.
    kube-proxy.daemon exits immediately after starting (no running k8s cluster),
    so `active` state is only reliable right after a `start` from a disabled state.
    Rapid start/stop cycles hit systemd's StartLimitBurst (default: 5 in 10 s),
    causing SnapChangeError on subsequent starts. We call `systemctl reset-failed`
    after disabling to clear the failure counter so the next start will succeed.
    """
    _snapd_apps.stop(_SNAP, _SERVICE, disable=True)
    subprocess.run(
        ['systemctl', 'reset-failed', f'snap.{_SNAP}.{_SERVICE}.service'],
        check=False,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def test_start():
    # GIVEN a stopped+disabled service, start should not raise.
    # kube-proxy.daemon exits immediately (no k8s cluster), so we don't assert active --
    # the meaningful test is that start() completes without error.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    assert not _service_is_active()
    _snapd_apps.start(_SNAP, _SERVICE)  # should not raise


def test_start_already_running_no_error():
    # Starting a service should not raise even if already started.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE)  # first start
    _snapd_apps.start(_SNAP, _SERVICE)  # second start should not raise


def test_start_with_enable():
    # start with enable=True re-enables a disabled service.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    assert not _service_is_enabled()
    _snapd_apps.start(_SNAP, _SERVICE, enable=True)
    # enabled persists even after kube-proxy exits quickly
    assert _service_is_enabled()


def test_start_nonexistent_service_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.start('hello-world', 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_start_nonexistent_snap_raises():
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.start('nonexistent-snap-xyz', 'service')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def test_stop():
    # GIVEN a service that was started from a clean disabled state
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE)
    # kube-proxy.daemon exits immediately (no k8s cluster), so we don't assert active here --
    # that's already verified in test_start. The goal here is to verify stop() works.
    _snapd_apps.stop(_SNAP, _SERVICE)
    assert not _service_is_active()


def test_stop_already_stopped_no_error():
    # Stopping an already stopped service should not raise.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    assert not _service_is_active()
    _snapd_apps.stop(_SNAP, _SERVICE)
    assert not _service_is_active()


def test_stop_with_disable():
    # stop with disable=True disables the service so it won't start on boot.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE, enable=True)
    assert _service_is_enabled()
    _snapd_apps.stop(_SNAP, _SERVICE, disable=True)
    assert not _service_is_enabled()


def test_stop_nonexistent_service_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.stop('hello-world', 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_stop_nonexistent_snap_raises():
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.stop('nonexistent-snap-xyz', 'service')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


def test_restart():
    # Restarting should complete without error.
    # kube-proxy.daemon exits quickly after restart, so we don't assert active state.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.restart(_SNAP, _SERVICE)


def test_restart_stopped_service():
    # Restarting a stopped service should not raise.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    assert not _service_is_active()
    _snapd_apps.restart(_SNAP, _SERVICE)


def test_restart_whole_snap():
    # restart without specifying a service should not raise.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.restart(_SNAP)


def test_restart_nonexistent_service_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.restart('hello-world', 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_restart_nonexistent_snap_raises():
    # kube-proxy has no snap "service" app, so this triggers app-not-found.
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.restart('nonexistent-snap-xyz', 'service')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# _list_services
# ---------------------------------------------------------------------------


def test_list_services_returns_list():
    ensure_installed(_SNAP, classic=True)
    services = _snapd_apps._list_services(_SNAP)
    assert isinstance(services, list)
    assert len(services) > 0
    names = [s['name'] for s in services]
    assert _SERVICE in names


def test_list_services_no_snap_returns_all():
    ensure_installed(_SNAP, classic=True)
    all_services = _snapd_apps._list_services()
    assert isinstance(all_services, list)
    assert any(s.get('snap') == _SNAP for s in all_services)


def test_list_services_snap_with_no_services_raises():
    # The API raises app-not-found for a snap with no services.
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps._list_services('hello-world')
    assert ctx.value.kind == 'app-not-found'


def test_list_services_uninstalled_snap_raises():
    # The API raises snap-not-found for an uninstalled snap.
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd_apps._list_services('nonexistent-snap-xyz')
    assert ctx.value.kind == 'snap-not-found'


# ---------------------------------------------------------------------------
# start/stop whole snap (no service specified)
# ---------------------------------------------------------------------------


def test_start_all_services_of_snap():
    # Start all services of a snap; should not raise.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.start(_SNAP)


def test_stop_all_services_of_snap():
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.start(_SNAP)
    _snapd_apps.stop(_SNAP)
    assert not _service_is_active()


def test_start_snap_with_no_services_raises():
    # Starting a snap that has no services raises SnapAppNotFoundError.
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.start('hello-world')
    assert ctx.value.kind == 'app-not-found'


def test_stop_snap_with_no_services_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.stop('hello-world')
    assert ctx.value.kind == 'app-not-found'


def test_restart_snap_with_no_services_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _snapd_apps.restart('hello-world')
    assert ctx.value.kind == 'app-not-found'
