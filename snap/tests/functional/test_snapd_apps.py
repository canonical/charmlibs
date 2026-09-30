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

# start, stop and restart share one implementation, so the argument and error contracts below
# are asserted for all three rather than once each.
_FUNCTIONS = [_snapd_apps.start, _snapd_apps.stop, _snapd_apps.restart]
_IDS = ['start', 'stop', 'restart']


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
    assert ctx.value._kind == 'app-not-found'


def test_start_multiple_services():
    # Several services at once, as a list rather than a bare name.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, [_SERVICE])  # Should not raise.


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
    assert ctx.value._kind == 'app-not-found'


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
    assert ctx.value._kind == 'app-not-found'


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
#
# Which error snapd answers with depends on the shape of the request. Naming the snap on its own
# is a typed snap-not-found, but naming a service inside it is app-not-found -- the same kind it
# uses for a service an installed snap doesn't have. start, stop and restart probe
# /v2/snaps/{snap} on app-not-found, so an absent snap is a _NotFoundError whichever way it was
# named, and AppNotFoundError is left meaning what it says. The raw responses are pinned below.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
@pytest.mark.parametrize(
    'services', [None, 'svc', ['svc'], []], ids=['all', 'one', 'list', 'none']
)
def test_not_installed_snap_raises_not_found(func: Any, services: Any):
    # Every form of the services argument reports an absent snap as the same type and kind,
    # including the empty list, which never reaches /v2/apps and is answered by the probe alone.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        func(_ABSENT_SNAP, services)
    assert ctx.value._kind == 'snap-not-found'
    assert _ABSENT_SNAP in str(ctx.value)


@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
@pytest.mark.parametrize('services', ['svc', ['svc'], []], ids=['one', 'list', 'none'])
def test_not_installed_snap_converted_error_wording(func: Any, services: Any):
    # The forms that reach the probe raise snapd's own /v2/snaps/{snap} error unchanged: a terse
    # message with the snap name in value, which str() surfaces. Same wording as conf's get().
    with pytest.raises(_errors.NotInstalledError) as ctx:
        func(_ABSENT_SNAP, services)
    assert ctx.value.message == 'snap not installed'
    assert str(ctx.value._value) == _ABSENT_SNAP
    assert str(ctx.value) == f'snap not installed ({_ABSENT_SNAP})'


@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
def test_not_installed_snap_unconverted_error_wording(func: Any):
    # Naming no service reaches snapd as the snap's own name, which it answers with a typed
    # snap-not-found -- already the error the library wants, so nothing is converted and snapd's
    # wording is passed through, as set/unset pass through the conf endpoint's. The type and kind
    # are what the library keeps consistent across endpoints, not the message.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        func(_ABSENT_SNAP, None)
    assert ctx.value.message == f'snap "{_ABSENT_SNAP}" not found'


@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
def test_not_installed_snap_error_is_not_chained(func: Any):
    # snapd's misleading app-not-found is suppressed ('raise ... from None'), so the traceback is
    # a single error that doesn't blame a service the caller may never have named.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        func(_ABSENT_SNAP, 'svc')
    assert ctx.value.__cause__ is None
    assert ctx.value.__suppress_context__


def test_raw_api_not_installed_snap_with_a_service_is_app_not_found():
    # Pin the raw snapd behaviour the conversion relies on: naming a service inside a snap that
    # isn't installed is app-not-found. Asserted at the _client level because start/stop/restart
    # convert it; if snapd ever reported the absent snap directly here, this fails loudly rather
    # than leaving the probe branch as untested dead code.
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.post('/v2/apps', body={'action': 'start', 'names': [f'{_ABSENT_SNAP}.svc']})
    assert ctx.value._kind == 'app-not-found'
    assert ctx.value.message == f'snap "{_ABSENT_SNAP}" has no service "svc"'


def test_raw_api_installed_snap_without_the_service_is_indistinguishable():
    # The other half of the conflation: the same kind and the same shape of message for a snap
    # that is installed. Nothing in the response tells the two apart, which is why the probe
    # exists rather than a check on the message.
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.post('/v2/apps', body={'action': 'start', 'names': [f'{_NO_SERVICES_SNAP}.svc']})
    assert ctx.value._kind == 'app-not-found'
    assert ctx.value.message == f'snap "{_NO_SERVICES_SNAP}" has no service "svc"'


def test_raw_api_not_installed_snap_alone_is_snap_not_found():
    # Naming the snap on its own is not conflated: snapd resolves the name before it looks for
    # services, so this is already the error the library wants and no probe is made for it.
    with pytest.raises(_errors._NotFoundError) as ctx:
        _client.post('/v2/apps', body={'action': 'start', 'names': [_ABSENT_SNAP]})
    assert ctx.value._kind == 'snap-not-found'
    assert ctx.value.message == f'snap "{_ABSENT_SNAP}" not found'


@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
def test_system_is_not_special_here(func: Any):
    # The conf and interfaces endpoints serve 'system' and 'core' whether or not the core snap is
    # installed, so their not-installed probe skips both names. /v2/apps has no such alias, so
    # they're probed like any other snap. Only 'system' is asserted on: it is never a snap, while
    # 'core' is an ordinary one that may or may not be installed on the test machine.
    with pytest.raises(_errors.NotInstalledError) as ctx:
        func('system', [])
    assert ctx.value._kind == 'snap-not-found'


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
    assert ctx.value._kind == 'app-not-found'


def test_stop_snap_with_no_services_raises():
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.stop(_NO_SERVICES_SNAP)
    assert ctx.value._kind == 'app-not-found'


def test_restart_snap_with_no_services_raises():
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_apps.restart(_NO_SERVICES_SNAP)
    assert ctx.value._kind == 'app-not-found'


# ---------------------------------------------------------------------------
# services=[] ("none of them") vs services=None ("all of them")
# ---------------------------------------------------------------------------


def test_empty_services_does_not_start_or_enable():
    # The distinction the tri-state exists for: an empty list of services must not widen into
    # "every service the snap has". Asserted on the enabled flag rather than active, since
    # kube-proxy.daemon exits immediately (no k8s cluster) but stays enabled.
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    assert not _service_is_enabled()
    _snapd_apps.start(_SNAP, [], enable=True)
    assert not _service_is_enabled()


def test_empty_services_does_not_stop_or_disable():
    ensure_installed_local(_SNAP)
    _stop_and_disable()
    _snapd_apps.start(_SNAP, _SERVICE, enable=True)
    assert _service_is_enabled()
    _snapd_apps.stop(_SNAP, [], disable=True)
    assert _service_is_enabled()
    _stop_and_disable()


@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
def test_empty_services_is_a_no_op_for_a_snap_with_no_services(func: Any):
    # This snap has no services at all, so naming them all is an error (asserted above) while
    # naming none of them is not: the request is never made, and only the snap is checked.
    ensure_installed_local(_NO_SERVICES_SNAP)
    assert func(_NO_SERVICES_SNAP, []) is None


# ---------------------------------------------------------------------------
# empty and blank service names
#
# The names go in a JSON body, so snapd sees a service name exactly as passed and reports it as
# a service that doesn't exist -- loudly, but only after a round trip, and it aborts the whole
# request, so a valid service named alongside it isn't acted on either. start, stop and restart
# reject empty and blank names up front instead. These go through _client to pin snapd's side.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('service', ['', ' ', '\t'])
@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
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
    assert ctx.value._kind == 'app-not-found'
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


# ---------------------------------------------------------------------------
# empty and non-canonical snap names -> ValueError
#
# The snap name goes in the request body here rather than a URL path, so snapd would answer for
# it -- but a name that isn't a single path segment can't be a snap, and the not-installed probe
# builds a path from it, so it's rejected up front for the same reasons as in conf and info.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('snap', ['', ' ', '.', '..', 'kube-proxy/daemon'])
@pytest.mark.parametrize(
    'services', [None, 'svc', ['svc'], []], ids=['all', 'one', 'list', 'none']
)
@pytest.mark.parametrize('func', _FUNCTIONS, ids=_IDS)
def test_invalid_snap_name_raises_value_error(func: Any, services: Any, snap: str):
    with pytest.raises(ValueError):
        func(snap, services)


@pytest.mark.parametrize(
    ('name', 'kind', 'message'),
    [
        ('', 'snap-not-found', 'snap "" not found'),
        ('kube-proxy/daemon', 'snap-not-found', 'snap "kube-proxy/daemon" not found'),
        # snapd splits a name on its first '.' before resolving it, so these two are read as a
        # service of the snap '' rather than as the name that was sent -- and land on the
        # app-not-found branch, where the probe would build a path out of an unusable name.
        ('.', 'app-not-found', 'snap "" has no service ""'),
        ('..', 'app-not-found', 'snap "" has no service "."'),
    ],
)
def test_raw_api_invalid_snap_name(name: str, kind: str, message: str):
    # What the rejection above stops us from sending. Nothing is lost by rejecting these names
    # client-side: snapd resolves none of them to a snap either.
    with pytest.raises(_errors.APIError) as ctx:
        _client.post('/v2/apps', body={'action': 'start', 'names': [name]})
    assert ctx.value._kind == kind
    assert ctx.value.message == message
