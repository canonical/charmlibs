# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The library-wide contract for an absent snap: a subclass of NotFoundError, never the base.

snapd sends the same ``snap-not-found`` kind whether a snap is missing from the system or from the
store, and only the message differs, with wording that varies by endpoint. So the client raises
the base type and the function that made the request narrows it, since only that function knows
what it asked for. These tests hold that rule to every public function.
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

# Every public function, called so that it reaches the client. Only reaching it matters here.
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
    # A new public function has to be added here, so which sense it reports is a decision.
    public = {name for name in snap.__all__ if inspect.isfunction(getattr(snap, name))}
    assert public == set(_CALLS)


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_no_public_function_raises_the_base_type(name: str, mock_client: MockClient):
    # Swallowing the error (remove) is fine: the rule is only about what escapes.
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
    # Narrowing must carry snapd's own data across, not substitute a message of our own.
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


# Only these consult the store, so only these can report the store sense.
_STORE_SENSE = {'ensure', 'install', 'refresh'}


@pytest.mark.parametrize('name', sorted(set(_CALLS) - _STORE_SENSE))
def test_functions_that_never_consult_the_store_report_the_local_sense(
    name: str, mock_client: MockClient
):
    # The store is never asked, so it can never be what was missing.
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
# Narrowing raises a new exception, so the traceback starts at the library function that narrowed
# and drops the client's frames. Those frames are the same boilerplate every time, and everything
# specific to the failure is on the exception itself.
#
# These mock the raw request layer rather than the client functions, so the real client frames
# exist and their absence is a fact about narrowing rather than about the mock.
# ---------------------------------------------------------------------------

_SOURCE_DIR = pathlib.Path(snap.__file__).parent

# Only remove is excluded: it answers absence with a falsy result, so there is no traceback.
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
    # The control: unnarrowed, the client's frames are there, so their absence below is real.
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
    # _from builds the exception and returns before the raise, so it never appears itself.
    with pytest.raises(NotFoundError) as ctx:
        _CALLS[name]()
    assert '_errors.py:_from' not in _library_frames(ctx.value)


@pytest.mark.parametrize('name', _RAISING)
def test_narrowed_errors_are_not_chained(name: str, mock_raw: MagicMock):
    # The error snapd sent is the error reported, only more specifically, so showing it twice
    # would be noise rather than context.
    with pytest.raises(NotFoundError) as ctx:
        _CALLS[name]()
    assert ctx.value.__cause__ is None
    assert ctx.value.__suppress_context__
