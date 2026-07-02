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

"""Snap operations implemented as direct calls to the snapd REST API."""

from __future__ import annotations

import logging
import typing
from typing import Any

from . import _client

logger = logging.getLogger(__name__)


# /v2/snaps/{snap}/conf


def get(snap: str, /, *keys: str) -> dict[str, Any]:
    """Get snap configuration.

    Args:
        snap: The name of the snap to read configuration from.
        keys: Configuration keys to read. Nested options may be accessed with dotted notation,
            for example ``server.port``. If omitted, all top-level configuration is returned.

    Returns:
        A dict mapping each requested key to its configured value. When no keys are given,
        the dict contains every top-level configuration option. A dotted key is returned as a
        single entry keyed by the dotted string.

    Raises:
        OptionNotFoundError: if the snap is not installed, or if a requested key is not set.
    """
    params = {'keys': ','.join(keys)} if keys else None
    config = _client.get(f'/v2/snaps/{snap}/conf', query=params)
    assert isinstance(config, dict)
    return typing.cast('dict[str, Any]', config)


def unset(snap: str, key: str, /, *keys: str) -> None:
    """Unset snap configuration keys.

    Unsetting a key that is not currently set is a no-op and does not raise.

    Args:
        snap: The name of the snap to unset configuration on.
        key: A configuration key to unset. Nested options may be addressed with dotted
            notation, for example ``server.port``.
        keys: Additional configuration keys to unset.

    Raises:
        NotFoundError: if the snap is not installed.
        ChangeError: if the snap's configure hook fails. This includes unsetting any
            configuration on a snap that does not define a configure hook.
    """
    _client.put(f'/v2/snaps/{snap}/conf', body=dict.fromkeys((key, *keys)))


# `unset` with no keys specified unsets all keys (!).
# This is intentionally not exposed in our unset function for safety.
# If we wanted to add this functionality, we would do so with a separate function, like this:
# def unset_all(snap: str) -> None:
#     """Unset all snap configuration keys."""
#     _client.put(f'/v2/snaps/{snap}/conf', body={})


# Defined last to minimise the chance of meaningfully shadowing the built-in set type.
def set(snap: str, config: dict[str, Any], /) -> None:  # noqa: A001 (shadowing a Python builtin)
    """Set snap configuration.

    Args:
        snap: The name of the snap to configure.
        config: A mapping of configuration keys to values. Values may be any JSON-serialisable
            type, including nested dicts and lists. Setting a key to ``None`` unsets it.
            Nested options may be addressed with dotted keys, for example ``server.port``.
            An empty mapping is accepted as a no-op.

    Raises:
        NotFoundError: if the snap is not installed.
        ChangeError: if the snap's configure hook fails. This includes setting any
            configuration on a snap that does not define a configure hook.
    """
    _client.put(f'/v2/snaps/{snap}/conf', body=config)
