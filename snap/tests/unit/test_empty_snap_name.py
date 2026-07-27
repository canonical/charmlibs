# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The library-wide contract for an empty snap name: ValueError, before any request."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from charmlibs import snap

if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import MockClient

# Every public function that takes a snap name, called with an empty one.
_CALLS: dict[str, Callable[[], object]] = {
    'alias': lambda: snap.alias('', 'lxc', 'testlxc'),
    'ensure': lambda: snap.ensure(''),
    'ensure_revision': lambda: snap.ensure_revision('', 1),
    'get': lambda: snap.get(''),
    'hold': lambda: snap.hold(''),
    'info': lambda: snap.info(''),
    'install': lambda: snap.install(''),
    'logs': lambda: snap.logs(''),
    'refresh': lambda: snap.refresh(''),
    'remove': lambda: snap.remove(''),
    'restart': lambda: snap.restart(''),
    'set': lambda: snap.set('', {'mykey': 'myval'}),
    'start': lambda: snap.start(''),
    'stop': lambda: snap.stop(''),
    'unhold': lambda: snap.unhold(''),
    'unset': lambda: snap.unset('', ['mykey']),
}

# The interface functions take (snap, name) pairs in which an empty snap name is meaningful --
# it selects the system snap, or asks snapd to resolve the side -- so they're exempt from the
# contract. unalias takes an alias rather than a snap name.
_NO_SNAP_NAME_ARGUMENT = {'connect', 'disconnect', 'unalias'}


def test_every_public_function_is_accounted_for():
    # A new public function taking a snap name must either honour the contract (and be listed
    # in _CALLS) or be deliberately exempted above.
    public = {name for name in snap.__all__ if inspect.isfunction(getattr(snap, name))}
    assert public == set(_CALLS) | _NO_SNAP_NAME_ARGUMENT


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_empty_snap_name_raises_value_error_without_request(name: str, mock_client: MockClient):
    with pytest.raises(ValueError, match='must not be empty'):
        _CALLS[name]()
    mock_client.get.assert_not_called()
    mock_client.get_logs.assert_not_called()
    mock_client.post.assert_not_called()
    mock_client.put.assert_not_called()
