#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _client.get, _client.post, and _client.put.

These tests exercise the HTTP transport layer directly against the real snapd socket,
verifying response decoding, async change waiting, error mapping, and edge cases.

Tests are ordered to minimise snap install/remove churn.
"""

from __future__ import annotations

import typing
import urllib.parse
from typing import Any

import pytest

from charmlibs.snap import _client, _errors
from conftest import (
    ensure_installed_local,
    ensure_installed_store,
    ensure_removed,
    retry_on_rate_limit,
)

# Snapd's own test snaps from the store, for the paths that need a real store snap: one to
# install and refresh, and the smallest classic-confined one for the classic error path.
# Published by snapd: https://github.com/canonical/snapd/tree/master/tests/lib/snaps
_STORE_SNAP = 'test-snapd-tools'
_CLASSIC_SNAP = 'test-snapd-classic-confinement'

# Locally-built snaps (tests/functional/snaps) stand in wherever a test needs some capability
# of a snap rather than a particular snap: one that accepts configuration, one that runs a
# service, and one with no apps at all.
_CONF_SNAP = 'test-configure-snap'
_SERVICE_SNAP = 'test-service-snap'
_NO_SERVICES_SNAP = 'test-snap'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# store snap INSTALLED — tests that need the snap present
# ---------------------------------------------------------------------------


def test_get_returns_dict():
    # A sync GET for a snap returns a dict result.
    ensure_installed_store(_STORE_SNAP)
    result = _client.get(f'/v2/snaps/{_STORE_SNAP}')
    assert isinstance(result, dict)
    assert result['name'] == _STORE_SNAP


def test_post_sync_error_snap_already_installed():
    ensure_installed_store(_STORE_SNAP)
    with pytest.raises(_errors._AlreadyInstalledError) as ctx:
        _client.post(f'/v2/snaps/{_STORE_SNAP}', body={'action': 'install'})
    assert ctx.value._kind == 'snap-already-installed'


def test_post_sync_error_app_not_found():
    ensure_installed_store(_STORE_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.post(
            '/v2/apps', body={'action': 'start', 'names': [f'{_STORE_SNAP}.nonexistentservice']}
        )
    assert ctx.value._kind == 'app-not-found'


def test_post_sync_error_no_kind():
    # An invalid action returns an error with no 'kind'.
    ensure_installed_store(_STORE_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _client.post(f'/v2/snaps/{_STORE_SNAP}', body={'action': 'invalid-action'})
    assert type(ctx.value) is _errors.APIError
    assert not ctx.value._kind


def test_post_snap_no_update_available():
    # snap-no-update-available is raised (not suppressed) at the _client level.
    ensure_installed_store(_STORE_SNAP, channel='latest/stable')
    with pytest.raises(_errors._NoUpdatesAvailableError) as ctx:
        retry_on_rate_limit(_client.post)(
            f'/v2/snaps/{_STORE_SNAP}', body={'action': 'refresh', 'channel': 'latest/stable'}
        )
    assert ctx.value._kind == 'snap-no-update-available'


def test_post_waits_for_async_change():
    # POST for an async operation waits until the change completes and does not raise.
    # Last test needing the store snap — leaves it removed.
    ensure_installed_store(_STORE_SNAP)
    _client.post(f'/v2/snaps/{_STORE_SNAP}', body={'action': 'remove'})
    # Verify the snap is actually gone.
    with pytest.raises(_errors._NotFoundError):
        _client.get(f'/v2/snaps/{_STORE_SNAP}')


# ---------------------------------------------------------------------------
# Error paths using a never-installed snap name (no state changes needed)
# ---------------------------------------------------------------------------


def test_get_sync_error_snap_not_found():
    # The client raises the *base* _NotFoundError for snapd's ambiguous 'snap-not-found' kind,
    # leaving it to the function that made the request to say which sense was meant. These
    # assertions pin that contract at the client layer; the library layer narrows it.
    with pytest.raises(_errors._NotFoundError) as ctx:
        _client.get(f'/v2/snaps/{_ABSENT_SNAP}')
    assert type(ctx.value) is _errors._NotFoundError
    assert ctx.value._kind == 'snap-not-found'
    # This endpoint is what _utils.check_installed probes with; its message is terse, with the
    # snap name in the response's 'value'. get()/connect()/disconnect() raise this very error
    # unchanged, relying on str() to surface the name rather than building their own message.
    assert ctx.value.message == 'snap not installed'
    assert str(ctx.value._value) == _ABSENT_SNAP
    assert str(ctx.value) == f'snap not installed ({_ABSENT_SNAP})'


def test_get_sync_error_no_kind():
    # An error response with no 'kind' field maps to the base APIError.
    with pytest.raises(_errors.APIError) as ctx:
        _client.get('/v2/nonexistent-endpoint')
    assert type(ctx.value) is _errors.APIError
    assert not ctx.value._kind


def test_put_sync_error_snap_not_found():
    # PUT conf on an absent snap raises the base type -- set()/unset() narrow it.
    with pytest.raises(_errors._NotFoundError) as ctx:
        _client.put(f'/v2/snaps/{_ABSENT_SNAP}/conf', body={'key': 'value'})
    assert type(ctx.value) is _errors._NotFoundError
    assert ctx.value._kind == 'snap-not-found'


def test_get_logs_error_snap_not_found():
    # Requesting logs for an absent snap raises the base type -- logs() narrows it.
    with pytest.raises(_errors._NotFoundError) as ctx:
        _client.get('/v2/logs', query={'names': _ABSENT_SNAP, 'n': 10})
    assert type(ctx.value) is _errors._NotFoundError
    assert ctx.value._kind == 'snap-not-found'


# ---------------------------------------------------------------------------
# classic confinement error path
# ---------------------------------------------------------------------------


def test_post_sync_error_snap_needs_classic():
    ensure_removed(_CLASSIC_SNAP)
    with pytest.raises(_errors.NeedsClassicError) as ctx:
        _client.post(f'/v2/snaps/{_CLASSIC_SNAP}', body={'action': 'install'})
    assert ctx.value._kind == 'snap-needs-classic'


# ---------------------------------------------------------------------------
# Tests using locally-built snaps (kept installed)
# ---------------------------------------------------------------------------


def test_get_returns_list():
    # GET /v2/apps returns a list result.
    ensure_installed_local(_SERVICE_SNAP)
    result = _client.get('/v2/apps', query={'select': 'service', 'names': _SERVICE_SNAP})
    assert isinstance(result, list)
    result = typing.cast('list[dict[str, Any]]', result)
    assert len(result) > 0


def test_get_with_query_params():
    # Query parameters are passed through and affect the result.
    ensure_installed_local(_CONF_SNAP)
    try:
        # Set two keys so we can retrieve a subset of them.
        _client.put(
            f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-key-a': 'alpha', 'test-key-b': 'beta'}
        )
        full = _client.get(f'/v2/snaps/{_CONF_SNAP}/conf')
        assert isinstance(full, dict)
        assert 'test-key-a' in full and 'test-key-b' in full
        # Request only one key via query params.
        subset = _client.get(f'/v2/snaps/{_CONF_SNAP}/conf', query={'keys': 'test-key-a'})
        assert isinstance(subset, dict)
        assert 'test-key-a' in subset
        assert 'test-key-b' not in subset
    finally:
        # Clean up.
        _client.put(f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-key-a': None, 'test-key-b': None})


def test_post_async_change_error_raises_snap_change_error():
    # An async change that fails raises ChangeError.
    ensure_installed_local(_CONF_SNAP)
    with pytest.raises(_errors.ChangeError):
        _client.post(
            '/v2/aliases',
            body={
                'action': 'alias',
                'snap': _CONF_SNAP,
                'app': 'nonexistent-app',
                'alias': 'test-alias-func',
            },
        )


def test_put_waits_for_async_change():
    # PUT /v2/snaps/{snap}/conf is async and should complete without error.
    ensure_installed_local(_CONF_SNAP)
    try:
        _client.put(f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-key-functional': 'test-value'})
        result = _client.get(f'/v2/snaps/{_CONF_SNAP}/conf', query={'keys': 'test-key-functional'})
        assert isinstance(result, dict)
        result = typing.cast('dict[str, Any]', result)
        assert result.get('test-key-functional') == 'test-value'
    finally:
        # Clean up.
        _client.put(f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-key-functional': None})


def test_put_no_body_raises():
    # PUT with no body (None) raises a base APIError: snapd can't decode EOF as patch values.
    ensure_installed_local(_CONF_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _client.put(f'/v2/snaps/{_CONF_SNAP}/conf')
    assert 'EOF' in ctx.value.message
    assert not ctx.value._kind


def test_put_empty_body_succeeds():
    # PUT with an empty body dict ({}) is accepted by snapd and is a no-op.
    ensure_installed_local(_CONF_SNAP)
    _client.put(f'/v2/snaps/{_CONF_SNAP}/conf', body={})  # Should not raise.


def test_poll_fails_fast_when_socket_missing():
    # Submit a real async change, then point the client at a missing socket while waiting on it.
    # A missing socket means snapd is absent, so the poll fails fast without retrying.
    ensure_installed_local(_CONF_SNAP)
    response = _client._json_request(
        'PUT', f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-gone-key': 'value'}
    )
    change = _client._decode(response)
    assert isinstance(change, _client._Change)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(_client, '_SOCKET_PATH', '/run/this-snapd-socket-does-not-exist.socket')
            with pytest.raises(_errors.SocketNotFoundError) as ctx:
                change.wait()
        assert 'this-snapd-socket-does-not-exist' in ctx.value.message
    finally:
        # snapd is still processing the original change; wait for it before cleaning up.
        change.wait()
        _client.put(f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-gone-key': None})


# ---------------------------------------------------------------------------
# Non-canonical paths: snapd's router redirects, and we report it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('path', 'location'),
    [
        # snapd registers its routes on a gorilla/mux router with path cleaning left on, so any
        # path containing '//', '/./' or '/../' is answered with a 301 to the cleaned path and an
        # empty body. '/v2/snaps//conf' is what an empty snap name used to build.
        ('/v2/snaps//conf', '/v2/snaps/conf'),
        ('/v2/snaps/..', '/v2'),
        ('/v2/snaps/../changes', '/v2/changes'),
    ],
)
def test_redirect_raises_bad_response_error(path: str, location: str):
    # We don't follow redirects: the snap names we interpolate into paths are validated and
    # encoded, so a redirect means a bug on our side or a change in snapd. Before this was
    # handled, the empty body of the 301 surfaced as a confusing 'Invalid JSON' error.
    with pytest.raises(_errors.BadResponseError) as ctx:
        _client.get(path)
    assert '301' in ctx.value.message  # snapd's router cleans the path with a permanent redirect.
    assert path in ctx.value.message  # The path we asked for.
    assert location in ctx.value.message  # Where snapd points us.
    assert 'Invalid JSON' not in ctx.value.message


def test_percent_encoded_separator_still_reaches_another_endpoint():
    # Why snap names are validated and not merely percent-encoded: snapd's router matches on the
    # *decoded* path, so '%2F' is still a path separator to it. A name of '<snap>/conf' encodes
    # to a single segment on the wire, but reaches /v2/snaps/<snap>/conf -- the configuration.
    ensure_installed_local(_CONF_SNAP)
    try:
        _client.put(f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-key-encoded': 'alpha'})
        segment = urllib.parse.quote(f'{_CONF_SNAP}/conf', safe='')
        assert '/' not in segment
        result = _client.get(f'/v2/snaps/{segment}')
        assert isinstance(result, dict)
        result = typing.cast('dict[str, Any]', result)
        assert result.get('test-key-encoded') == 'alpha'  # The conf, not the snap info.
        assert 'name' not in result
    finally:
        _client.put(f'/v2/snaps/{_CONF_SNAP}/conf', body={'test-key-encoded': None})


def test_get_logs_returns_list():
    # /v2/logs returns a list of dicts.
    ensure_installed_local(_SERVICE_SNAP)
    result = _client.get_logs(query={'names': _SERVICE_SNAP, 'n': 5})
    assert isinstance(result, list)


def test_get_logs_error_app_not_found():
    # A snap with no services returns an app-not-found error via the log stream.
    ensure_installed_local(_NO_SERVICES_SNAP)
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.get_logs(query={'names': _NO_SERVICES_SNAP, 'n': 10})
    assert ctx.value._kind == 'app-not-found'
