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

import dataclasses
import datetime
import logging
from typing import Any

from . import _client
from . import _utils

logger = logging.getLogger(__name__)


# /v2/logs


@dataclasses.dataclass
class LogEntry:
    timestamp: datetime.datetime
    message: str
    sid: str
    pid: int


def logs(*snaps: str, num_lines: int = 10) -> list[LogEntry]:
    query: dict[str, Any] = {'n': num_lines}
    if snaps:
        query['names'] = ','.join(snaps)
    result = _client.get('/v2/logs', query=query)
    # A log entry looks like:
    # {'timestamp': '2026-02-27T03:01:19.488008Z',
    #  'message': 'QMP: {"timestamp": {"seconds": 1772161279, "microseconds": 487649}, "event": "RTC_CHANGE", "data": {"offset": 0, "qom-path": "/machine/unattached/device[7]/rtc"}}',  # noqa: E501
    #  'sid': 'multipassd',
    #  'pid': '135506'}]
    # The snap CLI presents this as:
    # 2026-02-27T16:01:19+13:00 multipassd[135506]: QMP: {"timestamp": {"seconds": 1772161279, "microseconds": 487649}, "event": "RTC_CHANGE", "data": {"offset": 0, "qom-path": "/machine/unattached/device[7]/rtc"}}  # noqa: E501
    # We preserve the separate fields by parsing to a dataclass.
    assert isinstance(result, list)
    log_entries: list[LogEntry] = []
    for obj in result:
        try:
            log_entry = LogEntry(
                timestamp=_utils._parse_timestamp(obj['timestamp']),
                message=obj['message'],
                sid=obj['sid'],
                pid=int(obj['pid']),
            )
            log_entries.append(log_entry)
        except (KeyError, TypeError, ValueError) as e:  # noqa: PERF203
            logger.warning('Skipping log entry with unexpected format: %r (error: %r)', obj, e)
    return log_entries
