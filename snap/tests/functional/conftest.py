#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared helpers for functional tests."""

from __future__ import annotations

import functools
import logging
import random
import time
import typing
from typing import Any

from charmlibs import snap
from charmlibs.snap import _client, _functions
from charmlibs.snap import _snapd_snaps as _snapd

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import ParamSpec, TypeVar

    _P = ParamSpec('_P')
    _T = TypeVar('_T')

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


def ensure_installed(*snaps: str, channel: str | None = None, classic: bool = False) -> None:
    for snap_name in snaps:
        retry_on_rate_limit(snap.ensure)(snap_name, channel=channel, classic=classic, update=False)


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
