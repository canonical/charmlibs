#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Alive check: verify snapd is reachable and the snap store is accessible.

If this test fails, the other functional tests will likely also fail due to
snapd being unreachable or the snap store being unavailable.
"""

import typing
from typing import Any

from charmlibs.snap import _client


def test_snap_store_reachable():
    # GET /v2/find hits the snap store; a non-empty result confirms both snapd
    # and the store are reachable. 'name' is an exact-name lookup rather than a search, so the
    # one result can only be the snap asked for -- a 'q' search could be satisfied by anything
    # the store thought was relevant, including nothing at all once it stops matching.
    result = _client.get('/v2/find', query={'name': 'test-snapd-tools'})
    assert isinstance(result, list)
    result = typing.cast('list[dict[str, Any]]', result)
    assert len(result) > 0
