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

"""Snap log operations, implemented as calls to the snapd REST API's /v2/logs endpoint."""

from __future__ import annotations

import logging
import typing
from typing import Any

from . import _client, _utils

if typing.TYPE_CHECKING:
    import datetime

logger = logging.getLogger(__name__)


# /v2/logs


# Not a dataclass so we can cleanly provide a smaller API surface (e.g. no astuple).
class LogEntry:
    """A single snap log entry."""

    def __init__(self, timestamp: datetime.datetime, sid: str, pid: int, message: str):
        self._timestamp = timestamp
        self._sid = sid
        self._pid = pid
        self._message = message

    @property
    def timestamp(self) -> datetime.datetime:
        """The timestamp of the log entry as a datetime object."""
        return self._timestamp

    @property
    def message(self) -> str:
        """The log message itself."""
        return self._message

    @property
    def sid(self) -> str:
        """The syslog identifier.

        The name the process registered with syslog, typically the snap service name.
        """
        return self._sid

    @property
    def pid(self) -> int:
        """The process ID."""
        return self._pid

    def __repr__(self) -> str:
        return (
            f'LogEntry(timestamp={self._timestamp!r},'
            f' sid={self._sid!r},'
            f' pid={self._pid!r},'
            f' message={self._message!r})'
        )

    def __str__(self) -> str:
        return f'{self._timestamp} {self._sid}[{self._pid}]: {self._message}'


def logs(*snaps: str, limit: int | None = 10) -> list[LogEntry]:
    """Retrieve recent log entries for one or more snaps.

    Log entries are returned in chronological order: oldest first, newest last.

    Args:
        snaps: Snap names to retrieve logs for. If omitted, returns system-wide snap logs.
        limit: Maximum number of log entries to return. Must be a positive integer, or
            ``None`` to retrieve all available log entries (equivalent to ``snap logs -n all``).

    Returns:
        A list of :class:`LogEntry` objects, ordered oldest first. The list may contain
        fewer entries than ``limit`` if fewer are available. Malformed entries returned by
        snapd are skipped (and logged as warnings) rather than raising.

    Raises:
        ValueError: If ``limit`` is not ``None`` and is not a positive integer.
        NotFoundError: If a specified snap is not installed.
        AppNotFoundError: If a specified snap has no services.
    """
    if limit is None:
        # snapd treats n=-1 as "no limit": return all available log entries.
        n = -1
    elif limit <= 0:
        raise ValueError(f'limit must be a positive integer or None, not {limit!r}')
    else:
        n = limit
    query: dict[str, Any] = {'n': n}
    if snaps:
        query['names'] = ','.join(snaps)
    result = _client.get_logs(query=query)
    # A log entry looks like:
    # {'timestamp': '2026-02-27T03:01:19.488008Z',
    #  'message': 'QMP: {"timestamp": {"seconds": 1772161279, "microseconds": 487649}, "event": "RTC_CHANGE", "data": {"offset": 0, "qom-path": "/machine/unattached/device[7]/rtc"}}',  # noqa: E501
    #  'sid': 'multipassd',
    #  'pid': '135506'}]
    # The snap CLI presents this as:
    # 2026-02-27T16:01:19+13:00 multipassd[135506]: QMP: {"timestamp": {"seconds": 1772161279, "microseconds": 487649}, "event": "RTC_CHANGE", "data": {"offset": 0, "qom-path": "/machine/unattached/device[7]/rtc"}}  # noqa: E501
    # We preserve the separate fields by parsing to a LogEntry.
    log_entries: list[LogEntry] = []
    for obj in result:
        try:
            log_entry = LogEntry(
                timestamp=_utils.parse_timestamp(obj['timestamp']),
                sid=obj['sid'],
                pid=int(obj['pid']),
                message=obj['message'],
            )
            log_entries.append(log_entry)
        except (KeyError, TypeError, ValueError) as e:  # noqa: PERF203
            logger.warning('Skipping log entry with unexpected format: %r (error: %r)', obj, e)
    return log_entries
