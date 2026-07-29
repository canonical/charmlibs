# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_apps: start, stop, restart."""

from __future__ import annotations

import typing
from typing import Any

import pytest

from charmlibs.snap import _client, _errors, _snapd_apps
from conftest import ensure_installed_local

# A locally-built snap whose only app is a long-running daemon (tests/functional/snaps).
# It stays up once started, so service state is stable enough to assert on directly.
_SNAP = 'test-service-snap'
_SERVICE = 'daemon'
_QUALIFIED_SERVICE = f'{_SNAP}.{_SERVICE}'

# A locally-built snap with no apps at all, for the paths where a snap has no service to act on.
_NO_SERVICES_SNAP = 'test-snap'

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
    """Put test-service-snap.daemon into a known clean state: stopped and disabled.

    Called at the start of tests that need a predictable initial service state. The daemon runs
    until it is stopped, so it never fails on its own and start/stop cycles don't accumulate
    against systemd's start rate limit.
    """
    _snapd_apps.stop(_SNAP, _SERVICE, disable=True)


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def test_start():
    # GIVEN a stopped+disabled service, start should leave it running.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    assert not _service_is_active()
    _snapd_apps.start(_SNAP, _SERVICE)
    assert _service_is_active()


def test_start_already_running_no_error():
    # Starting a service should not raise even if already started.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE)  # First start.
    _snapd_apps.start(_SNAP, _SERVICE)  # Second start should not raise.


def test_start_with_enable():
    # start with enable=True re-enables a disabled service.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    assert not _service_is_enabled()
    _snapd_apps.start(_SNAP, _SERVICE, enable=True)
    assert _service_is_enabled()


def test_start_nonexistent_service_raises():
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.start(_NO_SERVICES_SNAP, 'nonexistentservice')
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
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE)
    assert _service_is_active()
    _snapd_apps.stop(_SNAP, _SERVICE)
    assert not _service_is_active()


def test_stop_already_stopped_no_error():
    # Stopping an already stopped service should not raise.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    assert not _service_is_active()
    _snapd_apps.stop(_SNAP, _SERVICE)
    assert not _service_is_active()


def test_stop_with_disable():
    # stop with disable=True disables the service so it won't start on boot.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE, enable=True)
    assert _service_is_enabled()
    _snapd_apps.stop(_SNAP, _SERVICE, disable=True)
    assert not _service_is_enabled()


def test_stop_nonexistent_service_raises():
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.stop(_NO_SERVICES_SNAP, 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_stop_nonexistent_snap_raises():
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.stop('nonexistent-snap-xyz', 'service')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


def test_restart():
    # Restarting should leave the service running.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.restart(_SNAP, _SERVICE)
    assert _service_is_active()


def test_restart_stopped_service():
    # Restarting a stopped service should not raise.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    assert not _service_is_active()
    _snapd_apps.restart(_SNAP, _SERVICE)


def test_restart_whole_snap():
    # restart without specifying a service should not raise.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.restart(_SNAP)


def test_restart_nonexistent_service_raises():
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.restart(_NO_SERVICES_SNAP, 'nonexistentservice')
    assert ctx.value.kind == 'app-not-found'


def test_restart_nonexistent_snap_raises():
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
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.start(_SNAP)


def test_stop_all_services_of_snap():
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.start(_SNAP)
    _snapd_apps.stop(_SNAP)
    assert not _service_is_active()


def test_start_snap_with_no_services_raises():
    # Starting a snap that has no services raises AppNotFoundError.
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.start(_NO_SERVICES_SNAP)
    assert ctx.value.kind == 'app-not-found'


def test_stop_snap_with_no_services_raises():
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.stop(_NO_SERVICES_SNAP)
    assert ctx.value.kind == 'app-not-found'


def test_restart_snap_with_no_services_raises():
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.restart(_NO_SERVICES_SNAP)
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# empty and blank service names
#
# The names go in a JSON body, so snapd sees a service name exactly as passed and reports it as
# a service that doesn't exist -- loudly, but only after a round trip, and it aborts the whole
# request, so a valid service named alongside it isn't acted on either. start, stop and restart
# reject empty and blank names up front instead. These go through _client to pin snapd's side.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('service', ['', ' ', '\t'])
@pytest.mark.parametrize(
    'func',
    [_snapd_apps.start, _snapd_apps.stop, _snapd_apps.restart],
    ids=['start', 'stop', 'restart'],
)
def test_empty_and_blank_service_names_raise_value_error(func: Any, service: str):
    ensure_installed_local(_SNAP)
    with pytest.raises(ValueError, match='service name must not be'):
        func(_SNAP, service)


@pytest.mark.parametrize('service', ['', ' ', ' daemon '])
def test_raw_api_unusable_service_name_is_not_found(service: str):
    # snapd names the service verbatim, without stripping it, so a padded name is not resolved
    # to the service it looks like -- it is simply a service that doesn't exist.
    ensure_installed_local(_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.post('/v2/apps', body={'action': 'restart', 'names': [f'{_SNAP}.{service}']})
    assert ctx.value.kind == 'app-not-found'
    assert f'has no service "{service}"' in ctx.value.message


def test_raw_api_unusable_service_name_aborts_the_whole_request():
    # A valid service named alongside an unusable one is not restarted: the request is rejected
    # as a whole, which is why rejecting the name client-side loses nothing.
    ensure_installed_local(_SNAP)
    with pytest.raises(_errors.AppNotFoundError):
        _client.post(
            '/v2/apps',
            body={'action': 'restart', 'names': [f'{_SNAP}.', f'{_SNAP}.{_SERVICE}']},
        )
