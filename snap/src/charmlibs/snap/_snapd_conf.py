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

from . import _client, _errors, _snapd_snaps

logger = logging.getLogger(__name__)


# /v2/snaps/{snap}/conf


# snapd's conf endpoints treat 'system' as an alias for 'core' and serve system configuration
# whether or not the core snap is installed.
# Note that /v2/snaps/system always 404s (it's a hardcoded alias, not a real snap), and
# /v2/snaps/core 404s when the core snap is absent (typical when no other snaps depend on it).
# For the purposes of this module, we can skip snap installed checks for both names.
_SYSTEM_NAMES = ('core', 'system')


# Getting one config value looks like get(s, k)[k]. In future we could add a get_one(s) helper.
# Get with no keys returns the entire config, following the CLI (get_all is unnecessary).
def get(snap: str, /, *keys: str) -> dict[str, Any]:
    """Get snap configuration.

    Args:
        snap: The name of the snap to read configuration from.
        keys: Configuration keys to read. Nested options may be accessed with dotted notation,
            for example ``server.port``. If omitted, all top-level configuration is returned.

    Returns:
        A dict mapping each requested key to its configured value. When no keys are given, the
        entire config is returned as a nested dict, empty if the snap has no configuration.
        Each dotted key queried is returned as a top-level entry. For example, if snap ``foo``
        has a config option ``server.port=8080``, and another option ``client.timeout=30``, then
        ``get('foo')`` returns ``{'server': {'port': 8080}, 'client': {'timeout': 30}}``, while
        ``get('foo', 'client.timeout')`` returns ``{'client.timeout': 30}``, and a mixture like
        ``get('foo', 'server', 'server.port')`` returns both a nested entry for ``server`` and a
        dotted entry for ``server.port``, like ``{'server': {'port': 8080}, 'server.port': 8080}``.

    Raises:
        NotFoundError: if the snap is not installed. Never raised for ``system`` or ``core``,
            whose configuration is served whether or not the core snap is installed.
        OptionNotFoundError: if a requested key has no value stored in the snap's configuration.
            Snap configuration is schemaless, so snapd does not distinguish between a key the
            snap doesn't recognise, a key that was never set, and a key that was unset. Any
            defaults a snap applies internally are invisible here unless its configure hook has
            stored them with ``snapctl set``.
    """
    params = {'keys': ','.join(keys)} if keys else None
    try:
        config = _client.get(f'/v2/snaps/{snap}/conf', query=params)
    except _errors.OptionNotFoundError:
        # NOTE: snapd reports option-not-found both for a missing key and for a missing snap.
        # The CLI returns 'error: snap "foo" has no "bar" configuration' in both cases,
        # but we can distinguish them here for symmetry with this endpoint's PUT behaviour.
        # Following PUT, NotFoundError isn't raised for system/core,
        # even if the core snap isn't installed.
        if snap not in _SYSTEM_NAMES:
            _snapd_snaps.info(snap)  # Raise NotFoundError if the snap is not installed.
        raise
    assert isinstance(config, dict)
    # NOTE: A query with no specific keys for a non-installed snap returns {},
    # indistinguishable from an installed snap with no configuration.
    # The CLI reports 'error: snap "foo" has no configuration' in both cases.
    # We adapt this to raise NotFoundError for a missing snap (except system/core),
    # and return the empty result for an installed snap with no configuration.
    if not keys and not config and snap not in _SYSTEM_NAMES:
        _snapd_snaps.info(snap)  # Raise NotFoundError if the snap is not installed.
    return typing.cast('dict[str, Any]', config)


# Unset with no keys is a meaningless no-op, indistinguishable from set with an empty dict.
# We forbid it at the signature level to minimise confusion.
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
            configuration on a snap that does not define a configure hook. A failed change
            is rolled back: no key from the request is unset.
    """
    # NOTE: snap-not-found is returned for a missing snap, but not for system or core,
    # even if the core snap isn't installed -- configuration changes are still applied.
    _client.put(f'/v2/snaps/{snap}/conf', body=dict.fromkeys((key, *keys)))


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
            configuration on a snap that does not define a configure hook, and configuration
            rejected by a validating configure hook. A failed change is rolled back: no key
            from the request is applied.
    """
    # NOTE: snap-not-found is returned for a missing snap, but not for system or core,
    # even if the core snap isn't installed -- configuration changes are still applied.
    _client.put(f'/v2/snaps/{snap}/conf', body=config)
