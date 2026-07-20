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
from typing import Any

import pytest

from charmlibs.snap import _client, _errors
from conftest import ensure_installed, ensure_removed

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# hello-world INSTALLED — tests that need the snap present
# ---------------------------------------------------------------------------


def test_get_returns_dict():
    # A sync GET for a snap returns a dict result.
    ensure_installed('hello-world')
    result = _client.get('/v2/snaps/hello-world')
    assert isinstance(result, dict)
    assert result['name'] == 'hello-world'


def test_post_sync_error_snap_already_installed():
    ensure_installed('hello-world')
    with pytest.raises(_errors._AlreadyInstalledError) as ctx:
        _client.post('/v2/snaps/hello-world', body={'action': 'install'})
    assert ctx.value.kind == 'snap-already-installed'


def test_post_sync_error_app_not_found():
    ensure_installed('hello-world')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.post(
            '/v2/apps', body={'action': 'start', 'names': ['hello-world.nonexistentservice']}
        )
    assert ctx.value.kind == 'app-not-found'


def test_post_sync_error_no_kind():
    # An invalid action returns an error with no 'kind'.
    ensure_installed('hello-world')
    with pytest.raises(_errors.Error) as ctx:
        _client.post('/v2/snaps/hello-world', body={'action': 'invalid-action'})
    assert not ctx.value.kind
    assert not isinstance(ctx.value, _errors.BadResponseError)


def test_post_snap_no_update_available():
    # snap-no-update-available is raised (not suppressed) at the _client level.
    ensure_installed('hello-world', channel='latest/stable')
    with pytest.raises(_errors._NoUpdatesAvailableError) as ctx:
        _client.post(
            '/v2/snaps/hello-world', body={'action': 'refresh', 'channel': 'latest/stable'}
        )
    assert ctx.value.kind == 'snap-no-update-available'


def test_post_waits_for_async_change():
    # POST for an async operation waits until the change completes and does not raise.
    # Last hello-world test — leaves the snap removed.
    ensure_installed('hello-world')
    _client.post('/v2/snaps/hello-world', body={'action': 'remove'})
    # Verify the snap is actually gone.
    with pytest.raises(_errors.NotFoundError):
        _client.get('/v2/snaps/hello-world')


# ---------------------------------------------------------------------------
# Error paths using a never-installed snap name (no state changes needed)
# ---------------------------------------------------------------------------


def test_get_sync_error_snap_not_found():
    # GET for an absent snap raises NotFoundError.
    with pytest.raises(_errors.NotFoundError) as ctx:
        _client.get(f'/v2/snaps/{_ABSENT_SNAP}')
    assert ctx.value.kind == 'snap-not-found'


def test_get_sync_error_no_kind():
    # An error response with no 'kind' field maps to the base Error.
    with pytest.raises(_errors.Error) as ctx:
        _client.get('/v2/nonexistent-endpoint')
    assert not ctx.value.kind


def test_put_sync_error_snap_not_found():
    # PUT conf on an absent snap raises NotFoundError.
    with pytest.raises(_errors.NotFoundError) as ctx:
        _client.put(f'/v2/snaps/{_ABSENT_SNAP}/conf', body={'key': 'value'})
    assert ctx.value.kind == 'snap-not-found'


def test_get_logs_error_snap_not_found():
    # Requesting logs for an absent snap raises NotFoundError.
    with pytest.raises(_errors.NotFoundError) as ctx:
        _client.get('/v2/logs', query={'names': _ABSENT_SNAP, 'n': 10})
    assert ctx.value.kind == 'snap-not-found'


# ---------------------------------------------------------------------------
# charmcraft error path
# ---------------------------------------------------------------------------


def test_post_sync_error_snap_needs_classic():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.NeedsClassicError) as ctx:
        _client.post('/v2/snaps/charmcraft', body={'action': 'install'})
    assert ctx.value.kind == 'snap-needs-classic'


# ---------------------------------------------------------------------------
# Tests using other snaps (lxd, kube-proxy, htop — kept installed)
# ---------------------------------------------------------------------------


def test_get_returns_list():
    # GET /v2/apps returns a list result.
    ensure_installed('kube-proxy', classic=True)
    result = _client.get('/v2/apps', query={'select': 'service', 'names': 'kube-proxy'})
    assert isinstance(result, list)
    result = typing.cast('list[dict[str, Any]]', result)
    assert len(result) > 0


def test_get_with_query_params():
    # Query parameters are passed through and affect the result.
    ensure_installed('lxd')
    try:
        # Set two keys so we can retrieve a subset of them.
        _client.put('/v2/snaps/lxd/conf', body={'test-key-a': 'alpha', 'test-key-b': 'beta'})
        full = _client.get('/v2/snaps/lxd/conf')
        assert isinstance(full, dict)
        assert 'test-key-a' in full and 'test-key-b' in full
        # Request only one key via query params.
        subset = _client.get('/v2/snaps/lxd/conf', query={'keys': 'test-key-a'})
        assert isinstance(subset, dict)
        assert 'test-key-a' in subset
        assert 'test-key-b' not in subset
    finally:
        # Clean up.
        _client.put('/v2/snaps/lxd/conf', body={'test-key-a': None, 'test-key-b': None})


def test_post_async_change_error_raises_snap_change_error():
    # An async change that fails raises ChangeError.
    ensure_installed('lxd')
    with pytest.raises(_errors.ChangeError):
        _client.post(
            '/v2/aliases',
            body={
                'action': 'alias',
                'snap': 'lxd',
                'app': 'nonexistent-app',
                'alias': 'test-alias-func',
            },
        )


def test_put_waits_for_async_change():
    # PUT /v2/snaps/{snap}/conf is async and should complete without error.
    ensure_installed('lxd')
    try:
        _client.put('/v2/snaps/lxd/conf', body={'test-key-functional': 'test-value'})
        result = _client.get('/v2/snaps/lxd/conf', query={'keys': 'test-key-functional'})
        assert isinstance(result, dict)
        result = typing.cast('dict[str, Any]', result)
        assert result.get('test-key-functional') == 'test-value'
    finally:
        # Clean up.
        _client.put('/v2/snaps/lxd/conf', body={'test-key-functional': None})


def test_put_no_body_raises():
    # PUT with no body (None) raises a base Error: snapd can't decode EOF as patch values.
    ensure_installed('lxd')
    with pytest.raises(_errors.Error) as ctx:
        _client.put('/v2/snaps/lxd/conf')
    assert 'EOF' in ctx.value.message
    assert not ctx.value.kind


def test_put_empty_body_succeeds():
    # PUT with an empty body dict ({}) is accepted by snapd and is a no-op.
    ensure_installed('lxd')
    _client.put('/v2/snaps/lxd/conf', body={})  # Should not raise.


def test_poll_fails_fast_when_socket_missing():
    # Submit a real async change, then point the client at a missing socket while waiting on it.
    # A missing socket means snapd is absent, so the poll fails fast without retrying.
    ensure_installed('lxd')
    response = _client._json_request('PUT', '/v2/snaps/lxd/conf', body={'test-gone-key': 'value'})
    change = _client._decode(response)
    assert isinstance(change, _client._Change)
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(_client, '_SOCKET_PATH', '/run/this-snapd-socket-does-not-exist.socket')
            with pytest.raises(_errors.ConnectionError) as ctx:
                change.wait()
        assert ctx.value.kind == 'charmlibs-snap-socket-not-found'
    finally:
        # snapd is still processing the original change; wait for it before cleaning up.
        change.wait()
        _client.put('/v2/snaps/lxd/conf', body={'test-gone-key': None})


def test_get_logs_returns_list():
    # /v2/logs returns a list of dicts.
    ensure_installed('kube-proxy', classic=True)
    result = _client.get_logs(query={'names': 'kube-proxy', 'n': 5})
    assert isinstance(result, list)


def test_get_logs_error_app_not_found():
    # A snap with no services returns an app-not-found error via the log stream.
    ensure_installed('htop')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _client.get_logs(query={'names': 'htop', 'n': 10})
    assert ctx.value.kind == 'app-not-found'
