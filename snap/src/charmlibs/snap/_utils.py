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

from . import _client, _errors


def probe_not_installed(snap: str) -> _errors.NotFoundError | None:
    """Probe whether the snap is installed, returning the typed error to raise if it isn't.

    Returns ``None`` when the snap is installed, and for the ``system``/``core`` aliases, which
    snapd serves whether or not the core snap is installed (so they are never treated as absent).
    Otherwise probes ``GET /v2/snaps/{snap}`` and, when snapd reports the snap absent, returns a
    :class:`NotFoundError` whose message names the snap, ready for the caller to ``raise``.

    The message is composed rather than passed through from the probe's own error, which says
    only 'snap not installed' with the name in ``value``. Naming the snap matches snapd's own
    wording on the conf PUT and interface endpoints, so every operation reports a missing snap
    the same way.

    Raise the returned error with ``from None`` when converting an error snapd has already
    reported, so the caller sees a single traceback instead of a chained one exposing this probe.
    """
    # NOTE: snapd's conf endpoints treat 'system' as an alias for 'core', and interface requests
    # remap 'system'/'core' to the snapd snap, so both names are served without the core snap.
    # /v2/snaps/system always 404s (a hardcoded alias, not a real snap) and /v2/snaps/core 404s
    # when the core snap is absent, so probing either would report a working call as not installed.
    if snap in ('system', 'core'):
        return None
    try:
        _client.get(f'/v2/snaps/{snap}')
    except _errors.NotFoundError:
        return _errors.NotFoundError(
            f'snap "{snap}" is not installed', kind='snap-not-found', value=snap
        )
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
