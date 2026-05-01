#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _client.get, _client.post, and _client.put.

These tests exercise the HTTP transport layer directly against the real snapd socket,
verifying response decoding, async change waiting, error mapping, and edge cases.
"""

import pytest

from charmlibs.snap import _client, _errors
from conftest import ensure_installed, ensure_removed

# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


def test_get_returns_dict():
    # A sync GET for a snap returns a dict result.
    ensure_installed('hello-world')
    result = _client.get('/v2/snaps/hello-world')
    assert isinstance(result, dict)
    assert result['name'] == 'hello-world'


def test_get_returns_list():
    # GET /v2/apps returns a list result.
    ensure_installed('kube-proxy', classic=True)
    result = _client.get('/v2/apps', query={'select': 'service', 'names': 'kube-proxy'})
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_with_query_params():
    # Query parameters are passed through and affect the result.
    ensure_installed('lxd')
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
    # Clean up.
    _client.put('/v2/snaps/lxd/conf', body={'test-key-a': None, 'test-key-b': None})


def test_get_sync_error_snap_not_found():
    # GET for an uninstalled snap raises SnapNotFoundError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _client.get('/v2/snaps/hello-world')
    assert ctx.value.kind == 'snap-not-found'


def test_get_sync_error_no_kind():
    # An error response with no 'kind' field maps to the base SnapError.
    with pytest.raises(_errors.SnapError) as ctx:
        _client.get('/v2/nonexistent-endpoint')
    assert not ctx.value.kind


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------


def test_post_waits_for_async_change():
    # POST for an async operation waits until the change completes and does not raise.
    ensure_installed('hello-world')
    _client.post('/v2/snaps/hello-world', body={'action': 'remove'})
    # Verify the snap is actually gone.
    with pytest.raises(_errors.SnapNotFoundError):
        _client.get('/v2/snaps/hello-world')


def test_post_sync_error_snap_already_installed():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAlreadyInstalledError) as ctx:
        _client.post('/v2/snaps/hello-world', body={'action': 'install'})
    assert ctx.value.kind == 'snap-already-installed'


def test_post_sync_error_snap_needs_classic():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.SnapNeedsClassicError) as ctx:
        _client.post('/v2/snaps/charmcraft', body={'action': 'install'})
    assert ctx.value.kind == 'snap-needs-classic'


def test_post_sync_error_app_not_found():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _client.post(
            '/v2/apps', body={'action': 'start', 'names': ['hello-world.nonexistentservice']}
        )
    assert ctx.value.kind == 'app-not-found'


def test_post_sync_error_no_kind():
    # An invalid action returns an error with no 'kind'.
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapError) as ctx:
        _client.post('/v2/snaps/hello-world', body={'action': 'invalid-action'})
    assert not ctx.value.kind
    assert not isinstance(ctx.value, _errors.SnapAPIError)


def test_post_async_change_error_raises_snap_change_error():
    # An async change that fails raises SnapChangeError.
    ensure_installed('lxd')
    with pytest.raises(_errors.SnapChangeError):
        _client.post(
            '/v2/aliases',
            body={
                'action': 'alias',
                'snap': 'lxd',
                'app': 'nonexistent-app',
                'alias': 'test-alias-func',
            },
        )


def test_post_snap_no_update_available():
    # snap-no-update-available is raised (not suppressed) at the _client level.
    ensure_installed('hello-world', channel='latest/stable')
    with pytest.raises(_errors._SnapNoUpdatesAvailableError) as ctx:
        _client.post(
            '/v2/snaps/hello-world', body={'action': 'refresh', 'channel': 'latest/stable'}
        )
    assert ctx.value.kind == 'snap-no-update-available'


# ---------------------------------------------------------------------------
# PUT
# ---------------------------------------------------------------------------


def test_put_waits_for_async_change():
    # PUT /v2/snaps/{snap}/conf is async and should complete without error.
    ensure_installed('lxd')
    _client.put('/v2/snaps/lxd/conf', body={'test-key-functional': 'test-value'})
    result = _client.get('/v2/snaps/lxd/conf', query={'keys': 'test-key-functional'})
    assert isinstance(result, dict)
    assert result.get('test-key-functional') == 'test-value'
    # Clean up.
    _client.put('/v2/snaps/lxd/conf', body={'test-key-functional': None})


def test_put_sync_error_snap_not_found():
    # PUT conf on a non-installed snap raises SnapNotFoundError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _client.put('/v2/snaps/hello-world/conf', body={'key': 'value'})
    assert ctx.value.kind == 'snap-not-found'


def test_put_no_body_raises():
    # PUT with no body (None) raises a base SnapError: snapd can't decode EOF as patch values.
    ensure_installed('lxd')
    with pytest.raises(_errors.SnapError) as ctx:
        _client.put('/v2/snaps/lxd/conf')
    assert 'EOF' in ctx.value.message
    assert not ctx.value.kind


def test_put_empty_body_succeeds():
    # PUT with an empty body dict ({}) is accepted by snapd and is a no-op.
    ensure_installed('lxd')
    _client.put('/v2/snaps/lxd/conf', body={})  # should not raise


# ---------------------------------------------------------------------------
# GET /v2/logs (special-cased streaming response)
# ---------------------------------------------------------------------------


def test_get_logs_returns_list():
    # /v2/logs returns a list of dicts.
    ensure_installed('kube-proxy', classic=True)
    result = _client.get('/v2/logs', query={'names': 'kube-proxy', 'n': 5})
    assert isinstance(result, list)


def test_get_logs_error_app_not_found():
    # A snap with no services returns an app-not-found error via the log stream.
    ensure_installed('vlc')
    with pytest.raises(_errors.SnapAppNotFoundError) as ctx:
        _client.get('/v2/logs', query={'names': 'vlc', 'n': 10})
    assert ctx.value.kind == 'app-not-found'


def test_get_logs_error_snap_not_found():
    # Requesting logs for a non-installed snap raises SnapNotFoundError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _client.get('/v2/logs', query={'names': 'hello-world', 'n': 10})
    assert ctx.value.kind == 'snap-not-found'
