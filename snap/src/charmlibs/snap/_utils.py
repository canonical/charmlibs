# Copyright 2021 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helpers shared across the snapd modules."""

from __future__ import annotations

import datetime
import sys
import urllib.parse

from . import _client, _errors


def snap_path_segment(snap: str) -> str:
    """Validate a snap name and encode it for use as a single URL path segment.

    Raises ValueError if the name is empty or would not be a single, canonical path segment.
    Percent-encoding alone is not enough to guarantee that:

    - snapd's router (gorilla/mux) matches on the *decoded* path, so ``%2F`` is still a path
      separator to it: without this check ``info('hello-world/conf')`` would reach
      ``/v2/snaps/hello-world/conf`` and return that snap's configuration.
    - ``urllib.parse.quote`` leaves ``.`` unencoded, so a ``.`` or ``..`` name would still make
      the path non-canonical, which mux answers with a ``301`` to the cleaned path.

    Encoding is still applied, so that characters such as ``?`` and ``#`` in a name are sent as
    part of the path instead of starting a query string or fragment.
    """
    raise_if_empty_or_blank(snap, 'snap name')
    if '/' in snap or snap in ('.', '..'):
        raise ValueError(f'snap name must be a single path segment, not {snap!r}')
    return urllib.parse.quote(snap, safe='')


def raise_if_empty_or_blank(value: str, what: str) -> None:
    """Raise ValueError if the value is empty or contains only whitespace.

    Both are caller programming errors, so we reject them before making a request rather than
    passing them to snapd, whose response depends on the endpoint (anything from a typed
    ``snap "" not found`` to a redirect with an empty body, or to being silently ignored).

    Use :func:`raise_if_blank` instead where snapd gives an empty value a meaning of its own.
    """
    if not value:
        raise ValueError(f'{what} must not be empty')
    raise_if_blank(value, what)


def raise_if_blank(value: str, what: str) -> None:
    """Raise ValueError if the value is non-empty but contains only whitespace.

    Separate from :func:`raise_if_empty_or_blank` for the interface functions, where an empty
    value is meaningful -- it selects the system snap, or asks snapd to resolve that side of the
    connection. A blank value is never meaningful anywhere: snapd either treats it as a name that
    can't exist, or (on the endpoints that take a comma-separated list) discards it entirely.
    """
    if value and not value.strip():
        raise ValueError(f'{what} must not be blank: {value!r}')


def raise_if_not_comma_list_safe(value: str, what: str) -> None:
    """Raise ValueError if the value would not survive snapd's comma-separated list parsing.

    Some snapd endpoints take several values in one query parameter, joined by commas. snapd
    parses these with ``strutil.CommaSeparatedList``, which splits on commas, strips whitespace
    from each field, and discards the empty ones. A value that doesn't survive that unchanged is
    silently turned into something other than what the caller asked for, so we reject it here:

    - an empty or blank value contributes no field at all, so the request means "all of them"
      rather than "this one" -- ``logs('')`` would return the logs of every snap on the system.
    - a value containing a comma contributes two or more fields, quietly querying values the
      caller never named.
    - a value padded with whitespace comes back stripped, so it addresses a different name than
      the caller passed, and any result is keyed by the stripped name.

    Python's :meth:`str.strip` and the ``unicode.IsSpace`` that snapd's Go implementation strips
    with agree on every whitespace character we've tested, including the ones they define
    separately (U+0085, U+00A0, U+1680, U+2000, U+3000), and agree that zero-width characters
    (U+200B, U+FEFF) are content rather than whitespace.
    """
    raise_if_empty_or_blank(value, what)
    if ',' in value:
        raise ValueError(f'{what} must not contain a comma: {value!r}')
    if value != value.strip():
        raise ValueError(f'{what} must not have leading or trailing whitespace: {value!r}')


def check_installed_or_system(snap: str) -> _errors.NotFoundError | None:
    """Return NotFoundError if the snap is not installed or a system/core alias.

    Returns ``None`` when the snap is installed, and for the ``system``/``core`` aliases, which
    snapd handles config and interfaces for whether or not the core snap is installed as a snap.
    Check if this system handling is appropriate if using this function with other snapd endpoints.
    Otherwise probes ``GET /v2/snaps/{snap}`` and returns snapd's own :class:`NotFoundError` when
    it reports the snap absent, ready for the caller to ``raise``.

    Raises ValueError for a name that can't be used as a path segment (see
    :func:`snap_path_segment`). Callers that reach this from an exception handler must skip
    empty names, so that a ValueError can't mask the error they're classifying.
    """
    # NOTE: snapd's conf endpoints treat 'system' as an alias for 'core', and interface requests
    # remap 'system'/'core' to the snapd snap, so both names are served without the core snap.
    # /v2/snaps/system always 404s (a hardcoded alias, not a real snap) and /v2/snaps/core 404s
    # when the core snap is absent, so probing either would report a working call as not installed.
    if snap in ('system', 'core'):
        return None
    path = f'/v2/snaps/{snap_path_segment(snap)}'
    try:
        _client.get(path)
    except _errors.NotFoundError as e:
        return e.with_traceback(None)  # Clean error with no traceback for the caller to raise.
    return None


def normalize_channel(channel: str) -> str:
    """Normalize a snap channel string to the form "track/risk".

    Channels may be specified as track or risk only, or as "track/risk" or "track/risk/branch".
    Snapd uses default values internally, but will record the *requested* value in the snap info.
    This function normalizes channels with no "/" to the form "track/risk" for easier comparison.
    """
    if not channel:
        return ''
    if '/' not in channel:
        if channel not in ('edge', 'beta', 'candidate', 'stable'):
            # Track only, append default risk.
            return f'{channel}/stable'
        # Risk only, prepend default track.
        return f'latest/{channel}'
    return channel


def parse_timestamp(timestamp: str) -> datetime.datetime:
    """Parse a snapd timestamp string to a datetime object.

    This can be dropped in favour of datetime.fromisoformat when we require Python 3.11+.
    """
    if sys.version_info >= (3, 11):
        return datetime.datetime.fromisoformat(timestamp)
    # Python 3.10 can't parse the fractional seconds with fromisoformat.
    # We parse the format manually here for Ubuntu 22.04 based charms.
    #
    # The snapd version that comes with Ubuntu 22.04 emits Z-suffixed timestamps, e.g.
    # 2026-02-27T03:01:19.488008Z
    #
    # Note: Newer snapd versions emit RFC3339 timestamps with timezone offsets, but we don't
    # need to handle them here since they're covered by fromisoformat in Python 3.11+.
    dt, ms = timestamp.removesuffix('Z').split('.')
    base = datetime.datetime.fromisoformat(dt).replace(tzinfo=datetime.timezone.utc)
    # datetime.timedelta only supports microsecond precision (first 6 digits of fractional secs).
    # Snapd timestamps may have higher precision (truncated) or fewer than 6 digits (right-padded
    # with zeros). E.g. '.13454' is 134540 μs, not 13454 μs. This matches fromisoformat in 3.11+.
    microseconds = datetime.timedelta(microseconds=int(ms[:6].ljust(6, '0')))
    return base + microseconds
