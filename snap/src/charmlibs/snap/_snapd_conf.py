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

"""Snap operations implemented as direct calls to the snapd REST API."""

from __future__ import annotations

import logging
from typing import Any

from . import _client

logger = logging.getLogger(__name__)


# /v2/snaps/{snap}/conf


def get(snap: str, /, *keys: str) -> dict[str, Any]:
    """Get snap configuration."""
    params = {'keys': ','.join(keys)} if keys else None
    config = _client.get(f'/v2/snaps/{snap}/conf', query=params)
    assert isinstance(config, dict)
    return config


def _get_one(snap: str, key: str, /) -> Any:  # pyright: ignore[reportUnusedFunction]
    """Get a single snap configuration key."""
    config = get(snap, key)
    return config[key]


def unset(snap: str, key: str, /, *keys: str) -> None:
    """Unset snap configuration keys."""
    _client.put(f'/v2/snaps/{snap}/conf', body=dict.fromkeys((key, *keys)))


def _unset_all(snap: str) -> None:  # pyright: ignore[reportUnusedFunction]
    """Unset all snap configuration keys."""
    _client.put(f'/v2/snaps/{snap}/conf', body={})


# Defined last to minimise the chance of meaningfully shadowing the built-in set type.
def set(snap: str, config: dict[str, Any], /) -> None:  # noqa: A001 (shadowing a Python builtin)
    """Set snap configuration."""
    _client.put(f'/v2/snaps/{snap}/conf', body=config)
