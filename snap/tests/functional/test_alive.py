#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Alive check: verify snapd is reachable and the snap store is accessible.

If this test fails, the other functional tests will likely also fail due to
snapd being unreachable or the snap store being unavailable.
"""

from charmlibs.snap import _client


def test_snap_store_reachable():
    # GET /v2/find hits the snap store; a non-empty result confirms both snapd
    # and the store are reachable.
    result = _client.get('/v2/find', query={'q': 'hello-world'})
    assert isinstance(result, list)
    assert len(result) > 0
