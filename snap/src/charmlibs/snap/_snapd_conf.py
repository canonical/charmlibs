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

"""Snap config operations implemented as direct calls to the snapd REST API."""

from __future__ import annotations

import logging
import typing

from . import _client, _errors, _utils

if typing.TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

logger = logging.getLogger(__name__)


# /v2/snaps/{snap}/conf


# Getting one config value looks like get(s, [k])[k]. In future we could add a get_one(s) helper.
# Get with keys=None returns the entire config, following the CLI (get_all is unnecessary).
def get(snap: str, keys: Iterable[str] | None = None) -> dict[str, Any]:
    """Get snap configuration.

    Args:
        snap: The name of the snap to read configuration from.
        keys: Configuration keys to read. Nested options may be accessed with dotted notation,
            for example ``['server.port']``. If ``None``, the full config is returned as a
            nested dict. If an empty iterable, an empty dict is returned if the snap is installed.
            Must not be a bare string.

    Returns:
        A dict mapping each requested key to its configured value. If all keys are requested
        (keys=None), the entire config is returned as a nested dict (empty if the snap has no
        configuration). If no keys are requested (keys=[]), an empty dict is returned if the snap
        is installed. Each dotted key queried is returned as a top-level entry.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if any
            requested key is empty, blank, contains a comma, or is padded with whitespace.
        TypeError: if ``keys`` is a string (must be a non-string iterable of strings, or ``None``).
        NotFoundError: if the snap is not installed. Never raised for ``system`` or ``core``,
            whose configuration is served whether or not the core snap is installed.
        OptionNotFoundError: if a requested key has no value stored in the snap's configuration.
            Snap configuration is schemaless, so snapd does not distinguish between a key the
            snap doesn't recognise, a key that was never set, and a key that was unset. Any
            defaults a snap applies internally are invisible here unless its configure hook has
            stored them with ``snapctl set``.

    ::

        # Full config.
        get('foo')  # {'server': {'port': 8080}, 'client': {'timeout': 30}}
        get('foo', keys=None)  # {'server': {'port': 8080}, 'client': {'timeout': 30}}
        # Querying specific keys.
        get('foo', ['client'])  # {'client': {'timeout': 30}}
        get('foo', ['client.timeout'])  # {'client.timeout': 30}
        get('foo', ['server', 'server.port'])  # {'server': {'port': 8080}, 'server.port': 8080}
        # Querying no keys.
        get('foo', keys=[])  # {}
        # Invalid keys argument.
        get('foo', keys='client')  # TypeError
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}/conf'
    if isinstance(keys, str):
        raise TypeError('keys must be an iterable of strings, or None (not a string)')
    if keys is not None:
        keys = list(keys)
        if not keys:
            # NOTE: snapd returns the full configuration if no keys are specified.
            # We pass this behaviour through for keys=None, but for keys=[] we return
            # an empty dict, since the caller explicitly requested no keys.
            if error := _utils.check_installed_or_system(snap):
                raise error
            return {}
        # NOTE: the keys are sent as one comma-separated query parameter, so a key that snapd's
        # parser alters is silently not the query the caller asked for. Keys that all parse away
        # to nothing are the dangerous case: the request becomes a request for the whole
        # configuration, which for a snap that isn't installed is answered with an empty result
        # -- so without this check, get('absent-snap', ['']) returned {} instead of raising
        # NotFoundError, because the probe below only runs for keys=None.
        if problem := _utils.comma_list(keys):
            raise ValueError(f'config key {problem} (keys={keys!r})')
        params = {'keys': ','.join(keys)}
    else:
        params = None
    try:
        config = _client.get(path, query=params)
    except _errors.OptionNotFoundError:
        # NOTE: snapd reports option-not-found both for a missing key and for a missing snap.
        # The CLI returns 'error: snap "foo" has no "bar" configuration' in both cases.
        # For symmetry with PUT (set/unset), we convert to NotFoundError here for a missing snap.
        if error := _utils.check_installed_or_system(snap):
            raise error from None
        raise
    # Empty result when all config was requested: error if the snap isn't installed.
    if (not config) and (keys is None) and (error := _utils.check_installed_or_system(snap)):
        # NOTE: snapd returns {} for an installed snap with no config and for a missing snap.
        # The CLI returns 'error: snap "foo" has no configuration' for a missing snap.
        # For symmetry with PUT (set/unset), we raise NotFoundError here for a missing snap.
        raise error
    assert isinstance(config, dict)
    return typing.cast('dict[str, Any]', config)


def unset(snap: str, keys: Iterable[str]) -> None:
    """Unset snap configuration keys.

    Unsetting a key that is not currently set is a no-op and does not raise.

    Args:
        snap: The name of the snap to unset configuration on.
        keys: Configuration keys to unset. Nested options may be addressed with dotted
            notation, for example ``['server.port']``. Must not be a bare string.
            An empty iterable is still passed to snapd, and may trigger the snap's config hook.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if
            any key is empty or blank.
        TypeError: if ``keys`` is a string (must be a non-string iterable of strings).
        NotFoundError: if the snap is not installed.
        ChangeError: if the snap's configure hook fails. This includes unsetting any
            configuration on a snap that does not define a configure hook. A failed change
            is rolled back: no key from the request is unset.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}/conf'
    if isinstance(keys, str):
        raise TypeError('keys must be an iterable of strings (not a string)')
    keys = list(keys)
    # NOTE: snapd rejects these itself, but only once the configure hook runs, as a ChangeError
    # reporting an 'internal error' for an empty key. We reject them up front, so that an
    # unusable key is the same ValueError here as it is for get().
    if problem := _utils.empty_or_blank(keys):
        raise ValueError(f'config key {problem} (keys={keys!r})')
    # NOTE: snap-not-found is returned for a missing snap, but not for system or core,
    # even if the core snap isn't installed -- configuration changes are still applied.
    # NOTE: Unset with no keys is a no-op (like set with an empty dict). We let snapd handle it.
    _client.put(path, body=dict.fromkeys(keys))


# Defined last to minimise the chance of meaningfully shadowing the built-in set type.
def set(snap: str, config: dict[str, Any]) -> None:  # noqa: A001 (shadowing a Python builtin)
    """Set snap configuration.

    Args:
        snap: The name of the snap to configure.
        config: A mapping of configuration keys to values. Values may be any JSON-serialisable
            type, including nested dicts and lists. Setting a key to ``None`` unsets it.
            Nested options may be addressed with dotted keys, for example ``server.port``.
            An empty mapping is accepted as a no-op.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if
            any key in ``config`` is empty or blank.
        NotFoundError: if the snap is not installed.
        ChangeError: if the snap's configure hook fails. This includes setting any
            configuration on a snap that does not define a configure hook, and configuration
            rejected by a validating configure hook. A failed change is rolled back: no key
            from the request is applied.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}/conf'
    # NOTE: as for unset, snapd only rejects these once the configure hook runs.
    if problem := _utils.empty_or_blank(config):
        raise ValueError(f'config key {problem} (keys={list(config)!r})')
    # NOTE: snap-not-found is returned for a missing snap, but not for system or core,
    # even if the core snap isn't installed -- configuration changes are still applied.
    # NOTE: Set with an empty dict is a no-op. We let snapd handle it.
    _client.put(path, body=config)
