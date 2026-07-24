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


def snap_installed(snap: str) -> bool:
    """Return whether the snap is installed, treating the system snap names as always installed.

    snapd treats ``'system'`` as an alias for ``'core'`` on its config endpoints, and remaps both
    ``'system'`` and ``'core'`` to the always-present snapd snap on its interface endpoints, so
    operations on these names succeed whether or not the core snap is installed. Those names are
    reported as installed without probing; any other name is probed with ``GET /v2/snaps/{snap}``.
    """
    # NOTE: snapd's conf endpoints treat 'system' as an alias for 'core', and interface requests
    # remap 'system'/'core' to the snapd snap, so both names are served without the core snap.
    # /v2/snaps/system always 404s (a hardcoded alias, not a real snap) and /v2/snaps/core 404s
    # when the core snap is absent, so probing either would report a working call as not installed.
    if snap in ('system', 'core'):
        return True
    try:
        _client.get(f'/v2/snaps/{snap}')
    except _errors.NotFoundError:
        return False
    return True


def not_installed_error(snap: str) -> _errors.NotFoundError:
    """Build the typed error to raise for a snap that isn't installed.

    The message matches snapd's own wording for this case, as returned by the conf PUT and the
    interface endpoints, so the error names the snap even when it was detected by the
    :func:`snap_installed` probe, whose ``GET /v2/snaps/{snap}`` reports only 'snap not installed'
    with the name in ``value``.

    Raise this with ``from None`` when converting an error snapd has already reported, so the
    caller sees a single traceback instead of a chained one exposing the internal probe.
    """
    return _errors.NotFoundError(
        f'snap "{snap}" is not installed', kind='snap-not-found', value=snap
    )


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
