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

"""Snap interface operations, implemented as calls to the snapd API's /v2/interfaces endpoint."""

from __future__ import annotations

from typing import Any

from . import _client, _errors, _utils

# /v2/interfaces


def connect(plug: tuple[str, str], slot: tuple[str, str] | str | None = None) -> None:
    """Connect a snap's plug to a slot.

    Connecting an already-connected plug and slot succeeds silently.

    Args:
        plug: The plug to connect, as a ``(snap, plug)`` pair. Both parts are required:
            snapd cannot resolve a plug from the snap name alone, and treats a missing
            snap name as an error.
        slot: The slot to connect to. May be given as:

            - a ``(snap, slot)`` pair. Either part may be ``""`` to have snapd resolve it.
              An empty slot resolves to the matching slot on the plug snap.
              An ``APIError`` is raised if the slot cannot be resolved unambiguously.
              An empty snap means the system snap.
            - a bare snap name, shorthand for ``(snap, '')``.
            - ``None`` (the default), shorthand for ``('', '')``.

    Raises:
        NotFoundError: if the plug snap or slot snap is not installed.
            Never raised for the system snap.
        APIError: if the plug is not fully specified (empty snap or plug name), if the named plug
            or slot does not exist, if the plug and slot interfaces do not match, or if the slot
            cannot be resolved unambiguously.
        ChangeError: if the operation fails after starting (for example, an interface hook errors).

    ::

        # Connect a plug to its auto-resolved system slot.
        connect(('mysnap', 'home'))
        # Connect a plug to the matching slot on a named snap.
        connect(('mysnap', 'network'), 'other-snap')
        # Connect a plug to an explicitly named slot.
        connect(('mysnap', 'content'), ('other-snap', 'content-slot'))
    """
    # NOTE: plug snap and plug name are required, we let snapd validate this.
    # Unlike the other modules, an empty snap name isn't rejected client-side here: it is
    # meaningful on the slot side (the system snap, or auto-resolution), snap names go in the
    # request body rather than the URL, and snapd's own message for an empty plug snap is clear
    # ('cannot resolve connection, plug snap name is empty').
    plug_snap, plug_name = _snap_and_name(plug)
    slot_snap, slot_name = _snap_and_name(slot)
    data = {
        'action': 'connect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap, 'slot': slot_name}],
    }
    try:
        _client.post('/v2/interfaces', body=data)
    except _errors.APIError:
        # Turn snapd's empty-kind 'snap is not installed' error into a typed NotFoundError.
        _raise_if_snaps_not_installed_or_system(plug_snap, slot_snap)
        raise


def disconnect(
    plug: tuple[str, str] | None = None,
    slot: tuple[str, str] | None = None,
    *,
    forget: bool = False,
) -> None:
    """Disconnect a plug from a slot.

    At least one of ``plug`` or ``slot`` must be specified. Each is a ``(snap, name)`` pair;
    unlike :func:`connect`, a bare snap name is not accepted, because snapd requires the
    plug or slot name to identify what to disconnect.

    An ``APIError`` is raised if neither side is specified or if a specified side does not
    specify the plug or slot name.

    An empty snap on either side means the system snap (mirroring :func:`connect`'s slot): for
    example ``('', 'mount-observe')`` refers to ``mount-observe`` on ``snapd``/``core``.

    Three forms are supported:

    - both ``plug`` and ``slot``: disconnect that specific plug-slot connection.
      An ``APIError`` is raised if they are not connected.
    - ``plug`` only: disconnect everything connected to that plug. No-op if nothing is connected.
    - ``slot`` only: disconnect everything connected to that slot. No-op if nothing is connected.

    Args:
        plug: The plug side, as a ``(snap, plug)`` pair. Omit to disconnect by slot only.
        slot: The slot side, as a ``(snap, slot)`` pair. Omit to disconnect by plug only.
        forget: If ``True``, also clear snapd's stored preference for this interface.
            snapd normally remembers manual changes and replays them across snap refreshes.
            An auto-connected interface you disconnect stays disconnected on refresh, while a
            manual :func:`connect` is preserved. ``forget=True`` erases that stored preference
            so the interface reverts to snapd's default auto-connection policy on the next refresh.

    Raises:
        NotFoundError: if the plug snap or slot snap is not installed.
            Never raised for the system snap.
        APIError: if neither ``plug`` nor ``slot`` names anything to disconnect, if the named plug
            or slot does not exist, or if the fully-specified plug and slot are not connected.
        ChangeError: if the operation fails after starting (for example, an interface hook errors).

    ::

        # Disconnect everything from a plug (no-op if nothing is connected).
        disconnect(('mysnap', 'home'))
        # Disconnect everything from a slot.
        disconnect(slot=('other-snap', 'content-slot'))
        # Disconnect one specific connection (raises if not connected).
        disconnect(('mysnap', 'content'), ('other-snap', 'content-slot'))
    """
    # NOTE: snapd rejects both sides being ('', ''), and either side being (snap, '').
    # We let snapd validate this.
    plug_snap, plug_name = _snap_and_name(plug)
    slot_snap, slot_name = _snap_and_name(slot)
    data: dict[str, Any] = {
        'action': 'disconnect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap, 'slot': slot_name}],
    }
    if forget:
        data['forget'] = True
    # NOTE: For a one-sided disconnect, snapd raises interfaces-unchanged if nothing is connected.
    # We suppress this to make disconnect symmetric with connect (following the snap CLI).
    # A two-sided disconnect raise a plain 'it is not connected' APIError, which we let raise.
    try:
        _client.post('/v2/interfaces', body=data)
    except _errors._InterfacesUnchangedError:
        pass  # Follow the snap CLI's lead and suppress this error.
    except _errors.APIError:
        # Turn snapd's empty-kind 'snap is not installed' error into a typed NotFoundError.
        _raise_if_snaps_not_installed_or_system(plug_snap, slot_snap)
        raise


def _snap_and_name(spec: tuple[str, str] | str | None) -> tuple[str, str]:
    """Normalise a plug or slot spec to a ``(snap, name)`` pair of strings."""
    if spec is None:
        return '', ''
    if isinstance(spec, str):
        return spec, ''
    snap, name = spec  # ValueError if not a 2-item pair.
    return snap, name


def _raise_if_snaps_not_installed_or_system(plug_snap: str, slot_snap: str) -> None:
    """Convert an empty-kind 'snap is not installed' API error into a typed NotFoundError.

    snapd validates the plug snap before the slot snap (daemon/api_interfaces.go), reporting a
    not-installed snap as an empty-kind ``APIError`` before any plug/slot resolution. We probe the
    named snaps in the same order -- plug snap first -- so the ``NotFoundError`` names the same
    snap snapd would blame. Empty (auto-resolved) sides are skipped, and the ``system``/``core``
    aliases are skipped because snapd serves them without the core snap being installed. If both
    named snaps are installed, this returns and the caller re-raises the original error.

    Skipping empty sides is load-bearing in two ways: the probe would raise ValueError for an
    empty name, masking the API error being classified, and ``/v2/snaps/`` 404s with a generic
    'not found' rather than listing snaps.
    """
    if plug_snap:
        _utils.raise_if_snap_not_installed_or_system(plug_snap)
    if slot_snap:
        _utils.raise_if_snap_not_installed_or_system(slot_snap)
