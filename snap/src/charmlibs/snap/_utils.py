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
    from collections.abc import Collection, Iterable


def snap_path_segment(snap: str) -> str:
    """Validate a snap name and encode it for use as a single URL path segment.

    Raises ValueError if the name is empty or would not be a single, canonical path segment
    (see :func:`raise_if_not_path_segment`).

    Encoding is applied, so that characters such as ``?`` and ``#`` in a name are sent as
    part of the path instead of starting a query string or fragment.
    """
    raise_if_not_path_segment(snap)
    return urllib.parse.quote(snap, safe='')


def check_installed(snap: str, *, skip_system: bool = False) -> _errors.NotFoundError | None:
    """Return snapd's own NotFoundError if the snap is not installed, otherwise ``None``.

    Probes ``GET /v2/snaps/{snap}`` and returns the :class:`NotFoundError` snapd answers with when
    it reports the snap absent, ready for the caller to ``raise``.

    Args:
        snap: The name of the snap to check.
        skip_system: If ``True``, treat ``system`` and ``core`` as installed without probing.
            Pass this for endpoints snapd serves under those names whether or not the core snap
            is installed: the conf endpoints treat ``system`` as an alias for ``core``, and
            interface requests remap ``system``/``core`` to the snapd snap. Leave it ``False``
            for endpoints where ``core`` is an ordinary snap and ``system`` names nothing at all,
            such as ``/v2/apps``.

    Raises ValueError for a name that can't be used as a path segment (see
    :func:`snap_path_segment`). Callers that reach this from an exception handler must have
    validated the name already, so that a ValueError can't mask the error they're classifying.
    """
    # NOTE: /v2/snaps/system always 404s (a hardcoded alias, not a real snap) and /v2/snaps/core
    # 404s when the core snap is absent, so probing either would report a working call -- on an
    # endpoint that serves these names specially -- as not installed.
    if skip_system and snap in ('system', 'core'):
        return None
    path = f'/v2/snaps/{snap_path_segment(snap)}'
    try:
        _client.get(path)
    except _errors.NotFoundError as e:
        return e.with_traceback(None)  # Clean error with no traceback for the caller to raise.
    return None


RISKS = ('stable', 'candidate', 'beta', 'edge')


def normalize_channel(channel: str) -> str:
    """Normalize a snap channel string to the form snapd reports it in.

    Channels may be specified as a track or risk only, or as "track/risk",
    "risk/branch", or "track/risk/branch". Snapd fills in the defaults and records the
    *resolved* value, so a channel must be normalized the same way before it can be
    compared with the channel from :func:`info`.

    This mirrors ``channel.Full`` in snapd: a lone risk gets the ``latest`` track, a lone
    track gets the ``stable`` risk, and a leading risk in a two part channel means the
    second part is a branch rather than a risk, so the ``latest`` track is filled in.
    """
    components = [c for c in channel.split('/') if c]
    if not components:
        return ''
    if len(components) == 1:
        # Either a risk, which takes the default track, or a track, which takes the default risk.
        return f'latest/{components[0]}' if components[0] in RISKS else f'{components[0]}/stable'
    if len(components) == 2 and components[0] in RISKS:
        # "risk/branch", which takes the default track.
        return f'latest/{components[0]}/{components[1]}'
    return '/'.join(components)


def resolve_channel(channel: str, tracking: str) -> str:
    """Resolve a requested channel against the channel a snap currently tracks.

    Returns the channel that snapd would end up tracking, so that a caller can tell whether
    a requested channel is the one already tracked, without making a request to snapd.

    A channel that starts with a risk inherits the track the snap is on, rather than the
    default ``latest`` track. For example, refreshing a snap that tracks ``3.6/stable`` to
    ``edge`` gives ``3.6/edge``, not ``latest/edge``. A channel that names a track doesn't
    inherit the risk, so refreshing that same snap to ``4.0`` gives ``4.0/stable``. This
    mirrors ``channel.Resolve`` in snapd.

    Args:
        channel: The requested channel, or an empty string to keep the tracked channel.
        tracking: The channel the snap currently tracks, as reported by ``Info.tracking``.
            Empty for a snap that isn't installed, or was installed from a local file.
    """
    if not channel:
        return tracking
    # A track can only be inherited from a channel that has one. The channel reported by snapd
    # is always normalized, so this is only empty for a snap with no channel to inherit from.
    track = tracking.partition('/')[0] if '/' in tracking else ''
    if track and channel.partition('/')[0] in RISKS:
        channel = f'{track}/{channel}'
    return normalize_channel(channel)


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


########################################################
# Normalising arguments that take one value or several #
########################################################


def as_list(values: str | Iterable[str]) -> list[str]:
    """Normalise an argument that accepts one value or several to a list.

    A bare string is one value, not an iterable of its characters: ``'abc'`` means ``['abc']``.
    Every other iterable is materialised, so that the caller can iterate it more than once --
    to validate the values and then send them.

    Callers whose argument also accepts ``None`` (meaning "all") handle that case themselves,
    so that ``None`` is never confused with an empty iterable (meaning "none").
    """
    return [values] if isinstance(values, str) else list(values)


#############################################################
# Rejecting values snapd can't use, before making a request #
#############################################################


def raise_if_not_path_segment(snap: str) -> None:
    """Raise ValueError if a snap name would not be a single, canonical URL path segment.

    Percent-encoding alone is not enough to guarantee that:

    - snapd's router (gorilla/mux) matches on the *decoded* path, so ``%2F`` is still a path
      separator to it: without this check ``info('hello-world/conf')`` would reach
      ``/v2/snaps/hello-world/conf`` and return that snap's configuration.
    - ``urllib.parse.quote`` leaves ``.`` unencoded, so a ``.`` or ``..`` name would still make
      the path non-canonical, which mux answers with a ``301`` to the cleaned path.

    Functions that send the snap name in a request body rather than the path check it too: a name
    that isn't a path segment can't be a snap, and :func:`check_installed` builds a path from it.

    The empty and blank checks are chained here rather than delegated to
    :func:`raise_if_empty_or_blank`, so that the error is raised no deeper in the traceback than
    any other check (see tests/unit/test_empty_or_blank.py).
    """
    problem = _empty(snap) or _blank(snap) or _path_segment(snap)
    if problem:
        raise ValueError(_message('snap name', problem, [snap]))


def raise_if_empty_or_blank(values: str | Collection[str], *, label: str) -> None:
    """Raise ValueError if a value is empty or contains only whitespace."""
    values = as_list(values)
    for value in values:
        problem = _empty(value) or _blank(value)
        if problem:
            raise ValueError(_message(label, problem, values))


def raise_if_blank(values: str | Collection[str], *, label: str) -> None:
    """Raise ValueError if a value is non-empty but contains only whitespace."""
    values = as_list(values)
    for value in values:
        problem = _blank(value)
        if problem:
            raise ValueError(_message(label, problem, values))


def raise_if_not_comma_list_safe(values: str | Collection[str], *, label: str) -> None:
    """Raise ValueError if a value would not survive snapd's comma-separated list parsing.

    These values are joined by commas into one query parameter, making a value with a comma
    indistinguishable from multiple values after our ``','.join``.

    Snapd drops empty or blank values entirely (confusing when no values means "all"), and
    silently strips leading and trailing whitespace (breaking ``get(s, [k])[k]``).
    """
    values = as_list(values)
    for value in values:
        problem = _empty(value) or _blank(value) or _comma(value) or _padding(value)
        if problem:
            raise ValueError(_message(label, problem, values))


def _empty(value: str) -> str | None:
    if not value:
        return 'must not be empty'
    return None


def _blank(value: str) -> str | None:
    if value and not value.strip():
        return f'must not be blank: {value!r}'
    return None


def _path_segment(value: str) -> str | None:
    if '/' in value or value in ('.', '..'):
        return f'must be a single path segment: {value!r}'
    return None


def _comma(value: str) -> str | None:
    if ',' in value:
        return f'must not contain a comma: {value!r}'
    return None


def _padding(value: str) -> str | None:
    if value != value.strip():
        return f'must not have leading or trailing whitespace: {value!r}'
    return None


def _message(label: str, problem: str, values: list[str]) -> str:
    if len(values) > 1:
        return f'{label} {problem} (in {values!r})'
    return f'{label} {problem}'
