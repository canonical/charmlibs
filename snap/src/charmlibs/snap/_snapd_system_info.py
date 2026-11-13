# Copyright 2026 Canonical Ltd.
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

"""System information reported by the snapd REST API."""

from __future__ import annotations

import logging
import typing

from . import _client, _errors

if typing.TYPE_CHECKING:
    from typing import Any

    from typing_extensions import Self

logger = logging.getLogger(__name__)

# /v2/system-info


class SystemInfo:
    """Information about the system, as reported by snapd."""

    def __init__(self, architecture: str):
        self._architecture = architecture

    @classmethod
    def _from_dict(cls, info_dict: dict[str, Any]) -> Self:
        return cls(architecture=info_dict['architecture'])

    @property
    def architecture(self) -> str:
        """The system architecture snapd and the snap store use to pick snap revisions.

        In Debian/snap naming: for example ``amd64``, ``arm64``, ``ppc64el``, or ``s390x``.
        The intended use is keying per-architecture data, such as a map from architecture
        to a pinned snap revision.

        This is snapd's (userspace) architecture, which can differ from ``uname -m`` --
        for example on a system running a 32-bit userspace over a 64-bit kernel.
        """
        return self._architecture

    def __repr__(self) -> str:
        return f'{type(self).__name__}(architecture={self.architecture!r})'


def system_info() -> SystemInfo:
    """Get information about the system as reported by snapd.

    Returns:
        A :class:`SystemInfo` object with information about the system.

    Raises:
        BadResponseError: if snapd's response isn't one we can read.
        Error: (or a subtype) if the information could not be retrieved for another reason.
    """
    result = _client.get('/v2/system-info')
    if not isinstance(result, dict):
        raise _errors.BadResponseError(
            message=f'Unexpected response type {type(result).__name__!r} for system information, expected a "dict"',  # noqa: E501
            response=result,
        )
    result = typing.cast('dict[str, Any]', result)
    try:
        return SystemInfo._from_dict(result)
    except (KeyError, TypeError, ValueError) as e:
        # A field we require is missing, or holds something we can't parse. Reported rather than
        # asserted, so that the documented contract -- every failure is an Error -- holds here too.
        raise _errors.BadResponseError(
            message=f"Could not read snapd's system information: {e!r}",
            response=result,
        ) from None
