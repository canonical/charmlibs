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

logger = logging.getLogger(__name__)

# /v2/system-info


def system_arch() -> str:
    """Get the system architecture as reported by snapd.

    This is the architecture snapd and the snap store use to pick snap revisions, in
    Debian/snap naming: for example ``amd64``, ``arm64``, ``ppc64el``, or ``s390x``.
    The intended use is keying per-architecture data, such as a map from architecture
    to a pinned snap revision.

    The value is snapd's (userspace) architecture, which can differ from ``uname -m`` --
    for example on a system running a 32-bit userspace over a 64-bit kernel.

    Returns:
        The architecture string, exactly as snapd reports it.

    Raises:
        BadResponseError: if snapd's response has no readable architecture.
        Error: (or a subtype) if the information could not be retrieved for another reason.
    """
    result = _client.get('/v2/system-info')
    if not isinstance(result, dict):
        raise _errors.BadResponseError(
            message=f'Unexpected response type {type(result).__name__!r} for system information, expected a "dict"',  # noqa: E501
            response=result,
        )
    result = typing.cast('dict[str, object]', result)
    architecture = result.get('architecture')
    if not isinstance(architecture, str) or not architecture:
        raise _errors.BadResponseError(
            message=f"Could not read snapd's system architecture: {architecture!r}",
            response=result,
        )
    return architecture
