# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The library-wide contract for empty and blank values: ValueError, before any request.

Empty and blank are separate contracts, because snapd gives an empty value a meaning of its own
on the interface endpoints. A blank value -- one that is not empty but contains only whitespace
-- is never meaningful anywhere, so every public function rejects it.
"""

from __future__ import annotations

import inspect
import pathlib
from typing import TYPE_CHECKING

import pytest

from charmlibs import snap

if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import MockClient

# Every name-like field of every public function, as a call that puts the given value in that
# field and passes something usable everywhere else. Empty and blank are both rejected.
_CALLS: dict[str, Callable[[str], object]] = {
    'alias': lambda v: snap.alias(v, 'lxc', 'testlxc'),
    'alias (app)': lambda v: snap.alias('lxd', v, 'testlxc'),
    'alias (alias)': lambda v: snap.alias('lxd', 'lxc', v),
    'ensure_installed': lambda v: snap.ensure_installed(v),
    'get': lambda v: snap.get(v),
    'get (key)': lambda v: snap.get('lxd', [v]),
    'get_one': lambda v: snap.get_one(v, 'mykey'),
    'get_one (key)': lambda v: snap.get_one('lxd', v),
    'hold': lambda v: snap.hold(v),
    'list_one': lambda v: snap.list_one(v),
    'install': lambda v: snap.install(v),
    'logs': lambda v: snap.logs(v),
    'refresh': lambda v: snap.refresh(v),
    'remove': lambda v: snap.remove(v),
    'restart': lambda v: snap.restart(v),
    'restart (service)': lambda v: snap.restart('lxd', v),
    'set': lambda v: snap.set(v, {'mykey': 'myval'}),
    'set (key)': lambda v: snap.set('lxd', {v: 'myval'}),
    'start': lambda v: snap.start(v),
    'start (service)': lambda v: snap.start('lxd', v),
    'stop': lambda v: snap.stop(v),
    'stop (service)': lambda v: snap.stop('lxd', v),
    'unalias': lambda v: snap.unalias(v),
    'unhold': lambda v: snap.unhold(v),
    'unset': lambda v: snap.unset(v, ['mykey']),
    'unset (key)': lambda v: snap.unset('lxd', [v]),
}

# The interface functions take (snap, name) pairs in which an empty value is meaningful -- it
# selects the system snap, or asks snapd to resolve that side of the connection -- so they are
# exempt from the empty contract, but not from the blank one.
_BLANK_ONLY_CALLS: dict[str, Callable[[str], object]] = {
    'connect (plug snap)': lambda v: snap.connect((v, 'home')),
    'connect (plug name)': lambda v: snap.connect(('lxd', v)),
    'connect (slot snap)': lambda v: snap.connect(('lxd', 'home'), (v, 'home')),
    'connect (slot name)': lambda v: snap.connect(('lxd', 'home'), ('other', v)),
    'connect (slot as a bare snap name)': lambda v: snap.connect(('lxd', 'home'), v),
    'disconnect (plug snap)': lambda v: snap.disconnect((v, 'home')),
    'disconnect (plug name)': lambda v: snap.disconnect(('lxd', v)),
    'disconnect (slot snap)': lambda v: snap.disconnect(slot=(v, 'home')),
    'disconnect (slot name)': lambda v: snap.disconnect(slot=('other', v)),
}

# A blank value is only ever a typo for something. The full set of characters Python and snapd
# agree are whitespace is covered in test_utils.py; one is enough to pin each call site.
_BLANK = ' '


def _function_names(calls: dict[str, Callable[[str], object]]) -> set[str]:
    return {name.split(' (')[0] for name in calls}


def test_every_public_function_is_accounted_for():
    # A new public function must honour the empty contract (and be listed in _CALLS), or be
    # deliberately exempted into _BLANK_ONLY_CALLS. Neither table may name a function twice.
    public = {name for name in snap.__all__ if inspect.isfunction(getattr(snap, name))}
    covered = _function_names(_CALLS)
    blank_only = _function_names(_BLANK_ONLY_CALLS)
    assert public == covered | blank_only
    assert not covered & blank_only


def _assert_no_request(mock_client: MockClient) -> None:
    mock_client.get.assert_not_called()
    mock_client.get_logs.assert_not_called()
    mock_client.post.assert_not_called()
    mock_client.put.assert_not_called()


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_empty_raises_value_error_without_request(name: str, mock_client: MockClient):
    with pytest.raises(ValueError, match='must not be empty'):
        _CALLS[name]('')
    _assert_no_request(mock_client)


@pytest.mark.parametrize('name', sorted(_CALLS))
def test_blank_raises_value_error_without_request(name: str, mock_client: MockClient):
    with pytest.raises(ValueError, match='must not be blank'):
        _CALLS[name](_BLANK)
    _assert_no_request(mock_client)


@pytest.mark.parametrize('name', sorted(_BLANK_ONLY_CALLS))
def test_blank_raises_for_the_interface_functions_too(name: str, mock_client: MockClient):
    with pytest.raises(ValueError, match='must not be blank'):
        _BLANK_ONLY_CALLS[name](_BLANK)
    _assert_no_request(mock_client)


@pytest.mark.parametrize('name', sorted(_BLANK_ONLY_CALLS))
def test_empty_is_passed_through_by_the_interface_functions(name: str, mock_client: MockClient):
    # The other half of the exemption: an empty value is meaningful here, so it reaches snapd.
    _BLANK_ONLY_CALLS[name]('')
    mock_client.post.assert_called_once()


def _library_frames(exc: BaseException) -> list[str]:
    """Return the library frames of a traceback, as ``module.py:function``."""
    source_dir = pathlib.Path(snap.__file__).parent
    frames: list[str] = []
    tb = exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        path = pathlib.Path(code.co_filename)
        if path.parent == source_dir:
            frames.append(f'{path.name}:{code.co_name}')
        tb = tb.tb_next
    return frames


def test_error_is_raised_one_frame_below_the_function_the_caller_called():
    # The check raises, so a charm's traceback shows the function it called and the check itself.
    # A charm's tracebacks end up in the Juju debug log, so the frames between the call and the
    # error are noise for whoever reads them: the single-value predicates the check chains
    # together return rather than raise, so none of them appear here.
    with pytest.raises(ValueError) as ctx:
        snap.logs(_BLANK)
    assert _library_frames(ctx.value) == [
        '_snapd_logs.py:logs',
        '_utils.py:raise_if_not_comma_list_safe',
    ]


# The functions that validate through snap_path_segment reach the check one frame deeper, since
# it returns the encoded name and so has to call the check itself. The /v2/apps functions are the
# same depth for a different reason: start, stop and restart share one implementation, and it
# calls the check. Neither is deeper than that, which is why raise_if_not_path_segment chains the
# empty and blank predicates itself rather than calling raise_if_empty_or_blank.
_MAX_FRAMES = 3

# Some public functions are compositions of other public functions rather than calls to an
# endpoint of their own, and don't check their arguments themselves: whichever function they
# reach first does it. That puts the check one or more frames deeper than the rule above
# allows, which is the price of not duplicating the check in a layer that doesn't own it.
#
# ensure_installed leaves the deepest traceback in the library -- ensure_installed, its
# _installed_info probe, list_one, snap_path_segment and the check. get_one delegates to get,
# which validates both the snap name and the key before making a request.
_COMPOSITE_FUNCTIONS = {'ensure_installed', 'get_one'}


@pytest.mark.parametrize('name', sorted(_CALLS) + sorted(_BLANK_ONLY_CALLS))
def test_no_call_buries_the_error_deeper_than_the_check(name: str, mock_client: MockClient):
    # As above, for every field: the error surfaces from the check, not from somewhere further in.
    if name in _COMPOSITE_FUNCTIONS:
        pytest.skip('validated by the function it delegates to, not by itself')
    calls = _CALLS if name in _CALLS else _BLANK_ONLY_CALLS
    with pytest.raises(ValueError) as ctx:
        calls[name](_BLANK)
    frames = _library_frames(ctx.value)
    assert len(frames) <= _MAX_FRAMES, frames
    assert frames[-1].startswith('_utils.py:raise_if_'), frames


@pytest.mark.parametrize('name', sorted(_COMPOSITE_FUNCTIONS))
def test_composite_functions_still_reject_before_any_request(name: str, mock_client: MockClient):
    # The exemption above is about where the error is raised, not whether it is: these still
    # reject an unusable name, and still do it before reaching snapd.
    with pytest.raises(ValueError, match='must not be blank'):
        _CALLS[name](_BLANK)
    _assert_no_request(mock_client)
