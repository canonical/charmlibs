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
import json
import pathlib
import traceback
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from charmlibs import snap
from charmlibs.snap import _client
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


# ---------------------------------------------------------------------------
# Traceback shape
#
# Narrowing raises a new exception, so its traceback starts at the library function that
# narrowed rather than carrying the client's frames. That is deliberate: a classified error is
# one the caller can act on, and the frames between the call and the raise are the same
# boilerplate every time -- noise in the Juju debug log a charm's traceback ends up in. Nothing
# is lost that isn't already on the exception (kind, message, value, status code) or in the
# DEBUG log the client writes for every request.
#
# These mock the raw request layer rather than the client functions, so the real client frames
# exist and their absence from the traceback is a fact about narrowing, not about the mock.
# ---------------------------------------------------------------------------

_SOURCE_DIR = pathlib.Path(snap.__file__).parent

# Every function that reports an absent snap by raising. Only remove is excluded: it answers
# absence with a falsy result rather than an error, so there is no traceback to check.
_RAISING = sorted(set(_CALLS) - {'remove'})


@pytest.fixture
def mock_raw(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch _request so the real client decodes a genuine snapd error response."""
    body = json.dumps({
        'type': 'error',
        'status-code': 404,
        'status': 'Not Found',
        'result': {'message': 'snap not found', 'kind': 'snap-not-found', 'value': 'lxd'},
    }).encode()
    response = SimpleNamespace(
        read=lambda: body, status=404, reason='Not Found', url='http://localhost/v2/snaps/lxd'
    )
    mocked = MagicMock(return_value=response)
    monkeypatch.setattr(_client, '_request', mocked)
    return mocked


def _library_frames(exc: BaseException) -> list[str]:
    return [
        f'{pathlib.Path(f.filename).name}:{f.name}'
        for f in traceback.extract_tb(exc.__traceback__)
        if pathlib.Path(f.filename).parent == _SOURCE_DIR
    ]


def test_the_client_really_does_add_frames(mock_raw: MagicMock):
    # The control for the tests below: reaching the client unnarrowed leaves its frames in the
    # traceback, so their absence afterwards is narrowing's doing and not the mock's.
    with pytest.raises(NotFoundError) as ctx:
        _client.get('/v2/snaps/lxd')
    assert '_client.py:get' in _library_frames(ctx.value)


@pytest.mark.parametrize('name', _RAISING)
def test_narrowed_traceback_stops_at_the_library(name: str, mock_raw: MagicMock):
    with pytest.raises(NotFoundError) as ctx:
        _CALLS[name]()
    frames = _library_frames(ctx.value)
    assert not any(f.startswith('_client.py') for f in frames), frames
    # Nor the probe's frames, for the functions that classify by making a second request.
    assert not any(f.startswith('_utils.py') for f in frames), frames


@pytest.mark.parametrize('name', _RAISING)
def test_narrowing_adds_no_frame_of_its_own(name: str, mock_raw: MagicMock):
    # _narrowed builds the exception and returns before the raise, so it never appears itself.
    with pytest.raises(NotFoundError) as ctx:
        _CALLS[name]()
    assert not any('_narrowed' in f for f in _library_frames(ctx.value))


@pytest.mark.parametrize('name', _RAISING)
def test_narrowed_errors_are_not_chained(name: str, mock_raw: MagicMock):
    # A single traceback: the error snapd sent is the error reported, only more specifically,
    # so showing it twice would be noise rather than context.
    with pytest.raises(NotFoundError) as ctx:
        _CALLS[name]()
    assert ctx.value.__cause__ is None
    assert ctx.value.__suppress_context__
