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
import typing

import pytest

from charmlibs import snap
from charmlibs.snap import _utils
from charmlibs.snap._errors import NotInstalledError, NotInStoreError, _NotFoundError

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import MockClient

# Every public function must be listed here, in one of:
# 1. EXCLUDE if snapd never sends snap-not-found.
# 2. CALLS with a call that reaches the store.
# List also in one of:
# 1. DOES_NOT_RAISE if snap-not-found is handled but not raised.
# 2. RAISES_NOT_IN_STORE if snap-not-found becomes NotInStoreError.
# Otherwise the call is assumed to raise NotInstalledError.
# The quota endpoints answer a kindless 404 or 400 of their own, never snap-not-found:
# get_quota, list_quotas, and remove_quota name a group, not a snap. ensure_quota reads
# through get_quota, and narrows not-installed snaps itself via its check_installed probes.
EXCLUDE = {
    'alias',
    'unalias',
    'unhold',
    'get_quota',
    'list_quotas',
    'remove_quota',
    'ensure_quota',
}
CALLS: dict[str, Callable[[], object]] = {
    'connect': lambda: snap.connect(('lxd', 'home')),
    'disconnect': lambda: snap.disconnect(('lxd', 'home')),
    'ensure_installed': lambda: snap.ensure_installed('lxd'),
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
    # set_quota's own request never gets snap-not-found from snapd (its failures are kindless),
    # but the probe it does on failure narrows one to NotInstalledError.
    'set_quota': lambda: snap.set_quota('my-group', 'lxd', memory=1024),
    'start': lambda: snap.start('lxd'),
    'stop': lambda: snap.stop('lxd'),
    'unset': lambda: snap.unset('lxd', ['mykey']),
}
DOES_NOT_RAISE = {'remove'}  # catches _NotFoundError but doesn't raise
RAISES_NOT_IN_STORE = {'ensure_installed', 'install'}


def _mock_error(mock_client: MockClient) -> _NotFoundError:
    error = _NotFoundError('some message', kind='some kind', value='some value', status_code=123)
    for mock in (mock_client.get, mock_client.get_logs, mock_client.post, mock_client.put):
        mock.side_effect = error
    return error


def test_every_public_function_is_accounted_for():
    public = {name for name in snap.__all__ if inspect.isfunction(getattr(snap, name))}
    assert public == set(CALLS) | EXCLUDE


@pytest.mark.parametrize('name', sorted(set(CALLS) - DOES_NOT_RAISE - RAISES_NOT_IN_STORE))
def test_raises_not_installed_error(name: str, mock_client: MockClient):
    error = _mock_error(mock_client)
    with pytest.raises(_NotFoundError) as exc:
        CALLS[name]()
    e = exc.value
    assert type(e) is not _NotFoundError, 'Must narrow to a subtype.'
    assert type(e) is NotInstalledError
    assert e.message == error.message
    assert e._value == error._value
    assert e._kind == error._kind
    assert e._status_code == error._status_code
    assert e._status == error._status


@pytest.mark.parametrize('name', sorted(RAISES_NOT_IN_STORE))
def test_raises_not_in_store_error(name: str, mock_client: MockClient):
    error = _mock_error(mock_client)
    with pytest.raises(_NotFoundError) as exc:
        CALLS[name]()
    e = exc.value
    assert type(e) is not _NotFoundError, 'Must narrow to a subtype.'
    assert type(e) is NotInStoreError
    assert e.message == error.message
    assert e._value == error._value
    assert e._kind == error._kind
    assert e._status_code == error._status_code
    assert e._status == error._status


@pytest.mark.parametrize('name', sorted(DOES_NOT_RAISE))
def test_does_not_raise(name: str, mock_client: MockClient):
    _mock_error(mock_client)
    CALLS[name]()  # Does not raise.


def test_refresh_also_raises_not_in_store_error(
    monkeypatch: pytest.MonkeyPatch, mock_client: MockClient
):
    """Refresh raises NotInstalledError if both the refresh and the check_installed probe fail.

    If the refresh fails with _NotFoundError but check_installed succeeds,
    then we raise NotInStoreError instead.
    """

    def check_installed(*args: object, **kwargs: object):
        return None

    error = _mock_error(mock_client)
    monkeypatch.setattr(_utils, 'check_installed', check_installed)
    with pytest.raises(_NotFoundError) as exc:
        CALLS['refresh']()
    e = exc.value
    assert type(e) is not _NotFoundError, 'Must narrow to a subtype.'
    assert type(e) is NotInStoreError
    assert e.message == error.message
    assert e._value == error._value
    assert e._kind == error._kind
    assert e._status_code == error._status_code
    assert e._status == error._status
