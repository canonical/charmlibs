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
import typing
import urllib.parse

from . import _client, _errors

if typing.TYPE_CHECKING:
    from collections.abc import Collection


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
    raise_if_empty_or_blank(snap, label='snap name')
    if '/' in snap or snap in ('.', '..'):
        raise ValueError(f'snap name must be a single path segment, not {snap!r}')
    return urllib.parse.quote(snap, safe='')


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


#############################################################
# Rejecting values snapd can't use, before making a request #
#############################################################


def raise_if_empty_or_blank(values: str | Collection[str], *, label: str) -> None:
    """Raise ValueError if a value is empty or contains only whitespace.

    Both are caller programming errors, so we reject them before making a request rather than
    passing them to snapd, whose response depends on the endpoint (anything from a typed
    ``snap "" not found`` to a redirect with an empty body, or to being silently ignored).

    Use :func:`raise_if_blank` where snapd gives an empty value a meaning of its own.
    """
    values = _list(values)
    for value in values:
        problem = _empty(value) or _blank(value)
        if problem:
            raise ValueError(_message(label, problem, values))


def raise_if_blank(values: str | Collection[str], *, label: str) -> None:
    """Raise ValueError if a value is non-empty but contains only whitespace.

    Separate from :func:`raise_if_empty_or_blank` for the interface functions, where an empty
    value is meaningful. A blank value never is: snapd reads it as a name that can't exist, or
    discards it entirely on the endpoints taking a comma-separated list.
    """
    values = _list(values)
    for value in values:
        problem = _blank(value)
        if problem:
            raise ValueError(_message(label, problem, values))


def raise_if_not_comma_list_safe(values: str | Collection[str], *, label: str) -> None:
    """Raise ValueError if a value would not survive snapd's comma-separated list parsing.

    These values are joined by commas into one query parameter, which snapd parses with
    ``strutil.CommaSeparatedList``: it splits on commas, strips each field, and discards the empty
    ones. A value that doesn't survive that unchanged silently becomes a different request:

    - an empty or blank value contributes no field, so the request means "all of them" --
      ``logs('')`` would return the logs of every snap on the system.
    - a value containing a comma contributes two or more fields.
    - a padded value comes back stripped, addressing a different name than the caller passed.

    Python's :meth:`str.strip` and the ``unicode.IsSpace`` snapd strips with agree on every
    whitespace character we've tested, so this mirrors snapd's rule rather than approximating it.
    """
    # NOTE: each value is checked completely before the next, so what's reported for a value
    # doesn't depend on the others. The message names the whole collection either way.
    values = _list(values)
    for value in values:
        problem = _empty(value) or _blank(value) or _comma(value) or _padding(value)
        if problem:
            raise ValueError(_message(label, problem, values))


def _list(values: str | Collection[str]) -> list[str]:
    """Normalise the argument to the list of values to check.

    A bare string is one value, not an iterable of one-character values. A mapping becomes its
    keys, keeping its values out of the error message -- a charm's config can hold secrets.
    """
    return [values] if isinstance(values, str) else list(values)


def _empty(value: str) -> str | None:
    """Describe an empty value, which is never a name, key, or alias snapd can use."""
    if not value:
        return 'must not be empty'
    return None


def _blank(value: str) -> str | None:
    """Describe a value that is not empty but is entirely whitespace.

    The value is quoted, since a blank one is invisible otherwise. An empty value is left to
    :func:`_empty`, so the checks that accept one can leave that predicate out of their chain.
    """
    if value and not value.strip():
        return f'must not be blank: {value!r}'
    return None


def _comma(value: str) -> str | None:
    """Describe a value containing a comma, which snapd would read as two values."""
    if ',' in value:
        return f'must not contain a comma: {value!r}'
    return None


def _padding(value: str) -> str | None:
    """Describe a value with surrounding whitespace, which snapd would strip."""
    if value != value.strip():
        return f'must not have leading or trailing whitespace: {value!r}'
    return None


def _message(label: str, problem: str, values: list[str]) -> str:
    """Build the error message, naming the whole collection when there was more than one value.

    Takes normalised values, so a mapping has already become its keys: see :func:`_list`. Returns
    rather than raising, so the raise happens in the caller and adds no traceback frame.
    """
    if len(values) > 1:
        return f'{label} {problem} (in {values!r})'
    return f'{label} {problem}'
