# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_apps: start, stop, restart."""

from __future__ import annotations

import subprocess
import typing
from typing import Any

import pytest

from charmlibs.snap import _client, _errors, _snapd_apps
from conftest import ensure_installed

_SNAP = 'kube-proxy'
_SERVICE = 'daemon'
_QUALIFIED_SERVICE = f'{_SNAP}.{_SERVICE}'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# Test helper and possible future candidate for library public API.
def _list_services(snap: str | None = None) -> list[dict[str, Any]]:
    """List snap services."""
    query = {'select': 'service'}
    if snap:
        query['names'] = snap
    services = _client.get('/v2/apps', query=query)
    assert isinstance(services, list)
    return typing.cast('list[dict[str, Any]]', services)


def _service_dict() -> dict[str, Any]:
    services = _list_services(_SNAP)
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
    causing ChangeError on subsequent starts. We call `systemctl reset-failed`
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
    _snapd_apps.start(_SNAP, _SERVICE)  # Should not raise.


def test_start_already_running_no_error():
    # Starting a service should not raise even if already started.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE)  # First start.
    _snapd_apps.start(_SNAP, _SERVICE)  # Second start should not raise.


def test_start_with_enable():
    # start with enable=True re-enables a disabled service.
    ensure_installed(_SNAP, classic=True)
    _stop_and_disable()
    assert not _service_is_enabled()
    _snapd_apps.start(_SNAP, _SERVICE, enable=True)
    # enabled persists even after kube-proxy exits quickly.
    assert _service_is_enabled()


def test_start_nonexistent_service_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.start('hello-world', 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_start_nonexistent_snap_raises():
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.start('nonexistent-snap-xyz', 'service')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def test_stop():
    # GIVEN a service that was started from a clean disabled state.
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
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.stop('hello-world', 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_stop_nonexistent_snap_raises():
    with pytest.raises(_errors.AppNotFoundError) as ctx:
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
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.restart('hello-world', 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_restart_nonexistent_snap_raises():
    # kube-proxy has no snap "service" app, so this triggers app-not-found.
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.restart('nonexistent-snap-xyz', 'service')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_start_not_installed_snap_raises_app_not_found():
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.start(_ABSENT_SNAP, 'svc')
    assert ctx.value.kind == 'app-not-found'


def test_stop_not_installed_snap_raises_app_not_found():
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.stop(_ABSENT_SNAP, 'svc')
    assert ctx.value.kind == 'app-not-found'


def test_restart_not_installed_snap_raises_app_not_found():
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.restart(_ABSENT_SNAP, 'svc')
    assert ctx.value.kind == 'app-not-found'


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
    # Starting a snap that has no services raises AppNotFoundError.
    ensure_installed('hello-world')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.start('hello-world')
    assert ctx.value.kind == 'app-not-found'


def test_stop_snap_with_no_services_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.stop('hello-world')
    assert ctx.value.kind == 'app-not-found'


def test_restart_snap_with_no_services_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.restart('hello-world')
    assert ctx.value.kind == 'app-not-found'
