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


# Get with keys=None returns the entire config, following the CLI (get_all is unnecessary).
# Reading a single value is get_one, defined below in terms of this function.
def get(snap: str, keys: str | Iterable[str] | None = None) -> dict[str, Any]:
    """Get snap configuration.

    Args:
        snap: The name of the snap to read configuration from.
        keys: Configuration keys to read, as a single key or an iterable of keys. Nested options
            may be accessed with dotted notation, for example ``'server.port'``. If ``None``, the
            full config is returned as a nested dict. If an empty iterable, an empty dict is
            returned if the snap is installed.

    Returns:
        A dict mapping each requested key to its configured value. If all keys are requested
        (keys=None), the entire config is returned as a nested dict (empty if the snap has no
        configuration). If no keys are requested (keys=[]), an empty dict is returned if the snap
        is installed. Each dotted key queried is returned as a top-level entry. A single key
        passed as a bare string is no different from passing it in a list: the result is still a
        dict, so use :func:`get_one` to read one value without unwrapping it yourself.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if a
            key is empty, blank, or contains a comma or surrounding whitespace.
        NotInstalledError: if the snap is not installed. Never raised for ``system`` or ``core``,
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
        get('foo', 'client')  # {'client': {'timeout': 30}}
        get('foo', ['client.timeout'])  # {'client.timeout': 30}
        get('foo', ['server', 'server.port'])  # {'server': {'port': 8080}, 'server.port': 8080}
        # Querying no keys.
        get('foo', keys=[])  # {}
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}/conf'
    keys = None if keys is None else _utils.as_list(keys)
    if keys is not None:
        if not keys:
            # NOTE: snapd returns the full configuration if no keys are specified.
            # We pass this behaviour through for keys=None, but for keys=[] we return
            # an empty dict, since the caller explicitly requested no keys.
            if error := _utils.check_installed(snap, skip_system=True):
                raise error
            return {}
        # NOTE: snapd strips whitespace and drops empty keys. We make them an error up front so
        # we correctly handle no specific keys requested, and so that get(s, [k])[k] holds.
        _utils.raise_if_not_comma_list_safe(keys, label='config key')
        params = {'keys': ','.join(keys)}
    else:
        params = None
    try:
        config = _client.get(path, query=params)
    except _errors.NotFoundError as e:
        # Configuration is read from an installed snap; the store is never consulted.
        raise _errors.NotInstalledError._from(e) from None
    except _errors.OptionNotFoundError:
        # NOTE: snapd reports option-not-found both for a missing key and for a missing snap.
        # The CLI returns 'error: snap "foo" has no "bar" configuration' in both cases.
        # For symmetry with PUT (set/unset), we probe and raise NotInstalledError instead.
        if error := _utils.check_installed(snap, skip_system=True):
            raise error from None
        raise
    # Empty result when all config was requested: error if the snap isn't installed.
    if (
        (not config)
        and (keys is None)
        and (error := _utils.check_installed(snap, skip_system=True))
    ):
        # NOTE: snapd returns {} for an installed snap with no config and for a missing snap.
        # The CLI returns 'error: snap "foo" has no configuration' for a missing snap.
        # For symmetry with PUT (set/unset), we raise NotInstalledError for a missing snap.
        raise error
    assert isinstance(config, dict)
    return typing.cast('dict[str, Any]', config)


def get_one(snap: str, key: str) -> Any:
    """Get the value of a single snap configuration key.

    ``get_one(snap, key)`` returns ``value``, while ``get(snap, key)`` returns ``{key: value}``.

    Args:
        snap: The name of the snap to read configuration from.
        key: The configuration key to read. Nested options may be accessed with dotted notation,
            for example ``'server.port'``.

    Returns:
        The configured value, which may be any JSON type, including a nested dict for a key
        that names a subtree.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if the
            key is empty, blank, or contains a comma or surrounding whitespace.
        NotInstalledError: if the snap is not installed. Never raised for ``system`` or ``core``,
            whose configuration is served whether or not the core snap is installed.
        OptionNotFoundError: if the key has no value stored in the snap's configuration. See
            :func:`get` for why snapd cannot distinguish an unrecognised key from an unset one.

    ::

        get_one('foo', 'client')  # {'timeout': 30}
        get_one('foo', 'client.timeout')  # 30
    """
    # NOTE: get() rejects any key its 'keys' query parameter would alter, and raises
    # OptionNotFoundError for a key that isn't set, so the result is keyed by exactly the key
    # requested and this subscript can't raise KeyError.
    return get(snap, [key])[key]


def unset(snap: str, keys: str | Iterable[str]) -> None:
    """Unset snap configuration keys.

    Unsetting a key that is not currently set is a no-op and does not raise.

    Args:
        snap: The name of the snap to unset configuration on.
        keys: Configuration keys to unset, as a single key or an iterable of keys. Nested options
            may be addressed with dotted notation, for example ``'server.port'``. An empty
            iterable is still passed to snapd, and may trigger the snap's config hook.

            Unlike :func:`get`, there is no ``None`` meaning "all keys": snapd has no request for
            it, and building one out of the keys :func:`get` reports would unset keys the caller
            never named.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment,
            or if a key is empty or blank.
        NotInstalledError: if the snap is not installed.
        ChangeError: if the snap's configure hook fails. This includes unsetting any
            configuration on a snap that does not define a configure hook. A failed change
            is rolled back: no key from the request is unset.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}/conf'
    keys = _utils.as_list(keys)
    # NOTE: snapd rejects empty or blank keys. We reject them up front for symmetry with get().
    _utils.raise_if_empty_or_blank(keys, label='config key')
    # NOTE: snap-not-found is returned for a missing snap, but not for system or core,
    # even if the core snap isn't installed -- configuration changes are still applied.
    # NOTE: Unset with no keys is a no-op (like set with an empty dict). We let snapd handle it.
    try:
        _client.put(path, body=dict.fromkeys(keys))
    except _errors.NotFoundError as e:
        # Configuration is applied to an installed snap; the store is never consulted.
        raise _errors.NotInstalledError._from(e) from None


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
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if a
            key in ``config`` is empty or blank.
        NotInstalledError: if the snap is not installed.
        ChangeError: if the snap's configure hook fails. This includes setting any
            configuration on a snap that does not define a configure hook, and configuration
            rejected by a validating configure hook. A failed change is rolled back: no key
            from the request is applied.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}/conf'
    # NOTE: snapd rejects empty or blank keys. We reject them up front for symmetry with get().
    _utils.raise_if_empty_or_blank(config, label='config key')
    # NOTE: snap-not-found is returned for a missing snap, but not for system or core,
    # even if the core snap isn't installed -- configuration changes are still applied.
    # NOTE: Set with an empty dict is a no-op. We let snapd handle it.
    try:
        _client.put(path, body=config)
    except _errors.NotFoundError as e:
        # Configuration is applied to an installed snap; the store is never consulted.
        raise _errors.NotInstalledError._from(e) from None
