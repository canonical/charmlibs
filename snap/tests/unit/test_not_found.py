# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The library-wide contract for an absent snap: a subclass of NotFoundError, never the base.

A snap operation can need the snap to be installed on the system, to be offered by the store, or
both. snapd doesn't distinguish the two: it answers with the ``snap-not-found`` kind either way,
with the same status code and the same value, so the response alone can't say which precondition
failed. Only the message differs, and matching on it is not an option -- snapd words condition A
three different ways (``'snap not installed'``, ``'snap "X" is not installed'``, ``'snap "X" not
found'``) and condition B as ``'snap not found'``, which the third of those contains.

So the client raises the base :class:`NotFoundError` for that kind, and the function that made the
request narrows it: it knows which preconditions it needed. This module holds that rule to every
public function, so that a caller can always tell "it isn't installed" from "the store doesn't
have it" -- the distinction that makes composing these functions possible.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from charmlibs import snap
from charmlibs.snap._errors import NotFoundError, NotInStoreError

if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import MockClient

# Every public function, called so that it reaches the client. The arguments are the usable ones
# from test_empty_or_blank.py's tables -- what matters here is only that a request is attempted.
_CALLS: dict[str, Callable[[], object]] = {
    'alias': lambda: snap.alias('lxd', 'lxc', 'testlxc'),
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
    'unalias': lambda: snap.unalias('testlxc'),
    'unhold': lambda: snap.unhold('lxd'),
    'unset': lambda: snap.unset('lxd', ['mykey']),
}


def test_every_public_function_is_accounted_for():
    # A new public function has to be added here, so that whether it can report an absent snap --
    # and as which sense -- is a decision someone made rather than one that defaulted.
    public = {name for name in snap.__all__ if inspect.isfunction(getattr(snap, name))}
    assert public == set(_CALLS)


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_no_public_function_raises_the_base_type(name: str, mock_client: MockClient):
    # Every client method raises the base, so whichever one a function reaches, and however many
    # requests it makes, the error it lets out must name which precondition failed. Functions
    # that swallow the error (remove) or never reach the client are fine -- the rule is only
    # about what escapes.
    error = NotFoundError('snap not found', kind='snap-not-found', value='lxd', status_code=404)
    for mock in (mock_client.get, mock_client.get_logs, mock_client.post, mock_client.put):
        mock.side_effect = error
    try:
        _CALLS[name]()
    except NotFoundError as e:
        assert type(e) is not NotFoundError, (
            f'{name} let the base NotFoundError escape: narrow it to NotInstalledError or'
            f' NotInStoreError, depending on which the operation needed.'
        )


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_narrowing_preserves_snapds_own_fields(name: str, mock_client: MockClient):
    # Narrowing rebuilds the error as a subclass, so it must carry snapd's own data across rather
    # than substituting a message of the library's own.
    error = NotFoundError('snap not found', kind='snap-not-found', value='lxd', status_code=404)
    for mock in (mock_client.get, mock_client.get_logs, mock_client.post, mock_client.put):
        mock.side_effect = error
    try:
        _CALLS[name]()
    except NotFoundError as e:
        assert e.message == 'snap not found'
        assert e.value == 'lxd'
        assert e.kind == 'snap-not-found'
        assert e._status_code == 404


# The two senses, and which functions can report each. A function that consults the store can
# report either; one that only ever acts on an installed snap can only report the local sense.
_STORE_SENSE = {'ensure', 'install', 'refresh'}


@pytest.mark.parametrize('name', sorted(set(_CALLS) - _STORE_SENSE))
def test_functions_that_never_consult_the_store_report_the_local_sense(
    name: str, mock_client: MockClient
):
    # These act on an installed snap, so an absent snap can only mean it isn't installed --
    # the store is never asked and so can never be what was missing.
    error = NotFoundError('snap not found', kind='snap-not-found', value='lxd', status_code=404)
    for mock in (mock_client.get, mock_client.get_logs, mock_client.post, mock_client.put):
        mock.side_effect = error
    try:
        _CALLS[name]()
    except NotFoundError as e:
        assert not isinstance(e, NotInStoreError), (
            f'{name} reported a missing store entry, but it never consults the store'
        )
