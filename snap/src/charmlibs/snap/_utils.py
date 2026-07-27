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
    raise_if_snap_name_empty(snap)
    if '/' in snap or snap in ('.', '..'):
        raise ValueError(f'snap name must be a single path segment, not {snap!r}')
    return urllib.parse.quote(snap, safe='')


def raise_if_snap_name_empty(snap: str) -> None:
    """Raise ValueError if the snap name is empty.

    An empty snap name is a caller programming error, so we reject it before making a request
    rather than passing it to snapd, whose response depends on the endpoint (anything from a
    typed ``snap "" not found`` to a redirect with an empty body).
    """
    if not snap:
        raise ValueError('snap name must not be empty')


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


def resolve_channel(channel: str, current: str) -> str:
    """Resolve a requested channel against the channel a snap currently tracks.

    Returns the channel that snapd would end up tracking, so that a caller can tell whether
    a requested channel is the one already tracked, without making a request to snapd.

    A channel that starts with a risk inherits the track the snap is on, rather than the
    default ``latest`` track. For example, refreshing a snap that tracks ``3.6/stable`` to
    ``edge`` gives ``3.6/edge``, not ``latest/edge``. A channel that names a track doesn't
    inherit the risk, so refreshing that same snap to ``4.0`` gives ``4.0/stable``. This
    mirrors ``channel.Resolve`` in snapd.

    Args:
        channel: The requested channel, or an empty string to keep the current channel.
        current: The channel the snap currently tracks, as reported by :func:`info`. Empty
            for a snap that isn't installed, or was installed from a local file.
    """
    if not channel:
        return current
    # A track can only be inherited from a channel that has one. The channel reported by snapd
    # is always normalized, so this is only empty for a snap with no channel to inherit from.
    track = current.partition('/')[0] if '/' in current else ''
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
