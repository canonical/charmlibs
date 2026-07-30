# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The library-wide contract for an absent snap: a subclass of _NotFoundError, never the base.

snapd sends the same ``snap-not-found`` kind whether a snap is missing from the system or from the
store, and only the message differs, with wording that varies by endpoint. So the client raises
the base type and the function that made the request narrows it, since only that function knows
what it asked for. These tests hold that rule to every public function.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from charmlibs import snap
from charmlibs.snap._errors import NotInStoreError, _NotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import MockClient

# Every public function, called so that it reaches the client. Only reaching it matters here.
_CALLS: dict[str, Callable[[], object]] = {
    'connect': lambda: snap.connect(('lxd', 'home')),
    'disconnect': lambda: snap.disconnect(('lxd', 'home')),
    'ensure': lambda: snap.ensure('lxd'),
    'get': lambda: snap.get('lxd'),
    'get_one': lambda: snap.get_one('lxd', 'mykey'),
    'hold': lambda: snap.hold('lxd'),
    'install': lambda: snap.install('lxd'),
    'list_one': lambda: snap.list_one('lxd'),
    'logs': lambda: snap.logs('lxd'),
    'refresh': lambda: snap.refresh('lxd'),
    'remove': lambda: snap.remove('lxd'),
    'restart': lambda: snap.restart('lxd'),
    'set': lambda: snap.set('lxd', {'mykey': 'myval'}),
    'start': lambda: snap.start('lxd'),
    'stop': lambda: snap.stop('lxd'),
    'unset': lambda: snap.unset('lxd', ['mykey']),
}
EXCLUDE = {'alias', 'unalias', 'unhold'}  # snapd never sends snap-not-found


def test_every_public_function_is_accounted_for():
    # A new public function has to be added here, so which sense it reports is a decision.
    public = {name for name in snap.__all__ if inspect.isfunction(getattr(snap, name))}
    assert public == set(_CALLS) | EXCLUDE


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_no_public_function_raises_the_base_type(name: str, mock_client: MockClient):
    # Swallowing the error (remove) is fine: the rule is only about what escapes.
    error = _NotFoundError('snap not found', kind='snap-not-found', value='lxd', status_code=404)
    for mock in (mock_client.get, mock_client.get_logs, mock_client.post, mock_client.put):
        mock.side_effect = error
    try:
        _CALLS[name]()
    except _NotFoundError as e:
        assert type(e) is not _NotFoundError, (
            f'{name} let the base _NotFoundError escape: narrow it to NotInstalledError or'
            f' NotInStoreError, depending on which the operation needed.'
        )


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_narrowing_preserves_snapds_own_fields(name: str, mock_client: MockClient):
    # Narrowing must carry snapd's own data across, not substitute a message of our own.
    error = _NotFoundError('snap not found', kind='snap-not-found', value='lxd', status_code=404)
    for mock in (mock_client.get, mock_client.get_logs, mock_client.post, mock_client.put):
        mock.side_effect = error
    try:
        _CALLS[name]()
    except _NotFoundError as e:
        assert e.message == 'snap not found'
        assert e.value == 'lxd'
        assert e.kind == 'snap-not-found'
        assert e._status_code == 404


# Only these consult the store, so only these can report the store sense.
_STORE_SENSE = {'ensure', 'install', 'refresh'}


@pytest.mark.parametrize('name', sorted(set(_CALLS) - _STORE_SENSE))
def test_functions_that_never_consult_the_store_report_the_local_sense(
    name: str, mock_client: MockClient
):
    # The store is never asked, so it can never be what was missing.
    error = _NotFoundError('snap not found', kind='snap-not-found', value='lxd', status_code=404)
    for mock in (mock_client.get, mock_client.get_logs, mock_client.post, mock_client.put):
        mock.side_effect = error
    try:
        _CALLS[name]()
    except _NotFoundError as e:
        assert not isinstance(e, NotInStoreError), (
            f'{name} reported a missing store entry, but it never consults the store'
        )
