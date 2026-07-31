#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared helpers for functional tests."""

from __future__ import annotations

import functools
import json
import logging
import random
import time
import typing
import uuid
from pathlib import Path
from typing import Any

from charmlibs import snap
from charmlibs.snap import _client, _functions
from charmlibs.snap import _snapd_snaps as _snapd

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import ParamSpec, TypeVar

    _P = ParamSpec('_P')
    _T = TypeVar('_T')

# Snaps built from source by setup.sh before the suite runs. Tests prefer these to store snaps
# wherever they need some capability of a snap rather than a particular snap, so that the suite
# neither downloads hundreds of megabytes nor depends on a real-world snap keeping its shape.
SNAPS_DIR = Path(__file__).parent / 'snaps'

# Bases whose snaps are held by the core snap: core when declared, and no base at all, since a
# snap that declares none gets core implicitly. snapd omits 'base' from /v2/snaps in that case.
_CORE_BASES = frozenset({None, 'core'})

# Enable debug logging from snap library during tests.
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
snap_logger = logging.getLogger(snap.__name__)
snap_logger.setLevel(logging.DEBUG)
snap_logger.addHandler(handler)


def retry_on_rate_limit(func: Callable[_P, _T]) -> Callable[_P, _T]:
    """Wrap ``func`` so store rate-limit (HTTP 429) failures are retried with backoff.

    The snap store rate-limits by client IP. snapd surfaces this as a kindless error
    with the message "too many requests" -- synchronously for store queries like /v2/find, and
    wrapped in a ChangeError (an APIError subclass) for async install/refresh. CI runners share
    egress IPs and run the functional matrix concurrently, so these 429s are transient: retry with
    exponential backoff rather than failing the run. Only rate-limit errors are retried, so tests
    asserting on a specific error still see that error unchanged.
    """

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        max_attempts = 5
        attempts = 0
        while True:
            if attempts > 0:
                # Exponential backoff with jitter: 5s-6s, 10s-12s, 20s-24s, 40s-48s, ...
                delay = 5 * 2 ** (attempts - 1) * random.uniform(1.0, 1.2)
                msg = 'snap store rate-limited; retrying in %.0fs (attempt %d/%d)'
                snap_logger.warning(msg, delay, attempts, max_attempts)
                time.sleep(delay)
            attempts += 1
            try:
                return func(*args, **kwargs)
            except snap.APIError as e:
                # "too many requests" from canonical/snapd's store/store.go (ErrTooManyRequests)
                if attempts >= max_attempts or 'too many requests' not in e.message.lower():
                    raise

    return wrapper


def ensure_removed(*snaps: str) -> None:
    for snap_name in snaps:
        if _functions._installed_info(snap_name) is not None:
            snap.remove(snap_name)


def ensure_installed_store(*snaps: str, channel: str | None = None, classic: bool = False) -> None:
    for snap_name in snaps:
        retry_on_rate_limit(snap.ensure_installed)(
            snap_name, channel=channel, classic=classic, update=False
        )


# Test helper for the parts of `snap list` the library deliberately doesn't implement: listing
# several snaps in one request, and listing every installed revision rather than just the current
# one. list_one covers the single-snap case charms actually need, and these calls are local and
# cheap, so a charm wanting several can loop -- which is why this lives here and not in the API.
def _list(  # pyright: ignore[reportUnusedFunction] (imported by the test modules)
    snaps: str | Iterable[str] | None,
    *,
    all: bool = False,  # noqa: A002 (shadowing a Python builtin)
) -> list[_snapd.InstalledInfo]:
    """List installed snaps, as `snap list` does.

    Args:
        snaps: Snap names to list, as a single name or an iterable of names. If ``None``, every
            installed snap is listed. If an empty iterable, nothing is listed.
        all: If ``True``, list every installed revision of each snap rather than only the current
            one, as `snap list --all` does. A snap keeps its previous revision after a refresh,
            so a name can appear more than once and the result is no longer one entry per snap.

    Unlike `snap list`, a name that isn't installed is not an error: /v2/snaps filters rather
    than failing, and nothing here reconstructs the error the CLI would print. That, and the
    per-revision result shape under ``all``, are the two reasons this isn't library API.
    """
    query: dict[str, str] = {}
    if snaps is not None:
        names = [snaps] if isinstance(snaps, str) else list(snaps)
        # NOTE: An empty 'snaps' value is not "no snaps" to snapd -- it parses away, leaving the
        # unfiltered query, which answers with every installed snap. So no names means no request.
        if not names:
            return []
        query['snaps'] = ','.join(names)
    if all:
        query['select'] = 'all'
    result = _client.get('/v2/snaps', query=query or None)
    assert isinstance(result, list)
    result = typing.cast('list[dict[str, str]]', result)
    return [_snapd.InstalledInfo._from_dict(info_dict) for info_dict in result]


def snaps_holding_core() -> list[str]:
    """Return the installed app snaps that hold the core snap, and so block its removal.

    An app snap is held by core when it runs on it: when it declares ``base: core``, or declares
    no base at all and so gets core implicitly. Only apps are considered, so that a base, os,
    snapd, gadget or kernel snap is never a candidate for removal no matter what it declares --
    none of those is something a test installed, and the last two would be catastrophic to remove.

    snapd is asked rather than a list being kept here on purpose: which snaps are installed
    depends on what every other module has done, so a hand-maintained list goes stale as soon as
    a test starts using a new snap -- and it fails far from the change, as an unrelated core test
    reporting 'snap is being used by snaps ...'.
    """
    # Raw dicts rather than _list(None): the base and type fields this reads aren't on
    # InstalledInfo, which carries what `snap list` prints.
    snaps = _client.get('/v2/snaps')
    assert isinstance(snaps, list)
    snaps = typing.cast('list[dict[str, Any]]', snaps)
    return [s['name'] for s in snaps if s.get('type') == 'app' and s.get('base') in _CORE_BASES]


def remove_core_blockers() -> None:
    """Remove every installed snap that would block removal of the core snap.

    Removes whatever is holding core rather than a fixed set, so this keeps working as modules
    add and drop snaps. Functional tests are already destructive to the machine they run on
    (hence the workshop container), so removing a snap the suite didn't install is acceptable.
    """
    ensure_removed(*snaps_holding_core())


# ---------------------------------------------------------------------------
# Provisional ack and install_local implementations
#
# Built directly on _client internals: sideloading and assertion upload are not yet part of the
# library's public API. Kept here rather than in a test module because several modules install
# locally-built snaps.
# ---------------------------------------------------------------------------


def ack(assertions_data: bytes) -> None:
    """Upload assertion(s) to snapd's local database (POST /v2/assertions)."""
    response = _client._request('POST', '/v2/assertions', data=assertions_data)
    response_dict = json.loads(response.read())
    if response_dict.get('type') == 'error':
        raise _client._make_error(response_dict)


def install_local(path: Path, *, dangerous: bool = False, classic: bool = False) -> None:
    """Install a local snap file via the snapd sideload API (POST /v2/snaps)."""
    boundary = uuid.uuid4().hex
    crlf = b'\r\n'

    def form_field(name: str, value: str) -> bytes:
        return b''.join([
            b'--',
            boundary.encode(),
            crlf,
            b'Content-Disposition: form-data; name="',
            name.encode(),
            b'"',
            crlf,
            crlf,
            value.encode(),
            crlf,
        ])

    body = [
        b'--',
        boundary.encode(),
        crlf,
        b'Content-Disposition: form-data; name="snap"; filename="',
        path.name.encode(),
        b'"',
        crlf,
        b'Content-Type: application/octet-stream',
        crlf,
        crlf,
        path.read_bytes(),
        crlf,
    ]
    if dangerous:
        body.append(form_field('dangerous', 'true'))
    if classic:
        body.append(form_field('classic', 'true'))
    body.extend([b'--', boundary.encode(), b'--', crlf])

    headers = {
        'Accept': 'application/json',
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    }
    response = _client._request('POST', '/v2/snaps', headers=headers, data=b''.join(body))
    response_dict = json.loads(response.read())
    if response_dict.get('type') == 'error':
        raise _client._make_error(response_dict)
    _client._Change(response_dict['change']).wait()


def ensure_installed_local(name: str, *, version: str = '1.0', classic: bool = False) -> None:
    """Ensure a snap built from ``SNAPS_DIR`` is installed, sideloading it if it is absent."""
    if _functions._installed_info(name) is not None:
        return
    install_local(SNAPS_DIR / f'{name}_{version}.snap', dangerous=True, classic=classic)


@functools.cache  # Cached to avoid repeated store queries.
def list_channels(snap: str) -> dict[str, _snapd.InstalledInfo]:
    """List information about all channels of a snap available in the store.

    Sources channel/revision info from the store, so that tests can assert against the
    revisions actually on each channel rather than hard-coding them.
    """
    results = _client.get('/v2/find', query={'name': snap})
    assert isinstance(results, list)
    results = typing.cast('list[dict[str, Any]]', results)
    # API returns a list of results, or an error if there are no matches.
    # We'll have one result for an exact name match.
    result, *_ = results
    channels = result['channels']
    # Store results are keyed by channel and have no tracking channel, so the key is supplied as
    # both: Info.tracking reads 'tracking-channel', which only an installed snap has.
    return {
        k: _snapd.InstalledInfo._from_dict({
            'name': snap,
            'channel': k,
            'tracking-channel': k,
            **v,
        })
        for k, v in channels.items()
    }
