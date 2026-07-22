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


def _snap_and_name(spec: tuple[str, str] | str | None) -> tuple[str, str]:
    """Normalise a plug or slot spec to a ``(snap, name)`` pair of strings.

    ``None`` becomes ``('', '')`` (fully unspecified: left for snapd to resolve or reject), and
    a bare snap name becomes ``(snap, '')`` (name left for snapd to resolve or reject). A pair is
    returned as-is; anything that is not a 2-item pair fails here with a clear ``ValueError``
    (this is also what rejects a bare string where only a pair is accepted -- the whole string
    is treated as the snap name, so it can never be silently split into characters).
    """
    if spec is None:
        return '', ''
    if isinstance(spec, str):
        return spec, ''
    snap, name = spec
    return snap, name


def _raise_not_installed_snap(plug_snap: str, slot_snap: str) -> None:
    """Convert an empty-kind 'snap is not installed' API error into a typed NotFoundError.

    snapd validates the plug snap before the slot snap (daemon/api_interfaces.go), reporting a
    not-installed snap as an empty-kind ``APIError`` before any plug/slot resolution. We probe the
    named snaps in the same order -- plug snap first -- so the ``NotFoundError`` names the same
    snap snapd would blame. Empty (auto-resolved) sides are skipped, and the ``system``/``core``
    aliases are skipped because snapd serves them without the core snap being installed. If both
    named snaps are installed, this returns and the caller re-raises the original error.
    """
    for snap in (plug_snap, slot_snap):
        if snap:
            _utils.raise_if_snap_not_installed_or_system(snap)


def connect(plug: tuple[str, str], slot: tuple[str, str] | str | None = None) -> None:
    """Connect a snap's plug to a slot.

    Connecting an already-connected plug and slot succeeds silently.

    Args:
        plug: The plug to connect, as a ``(snap, plug)`` pair. Both parts are required:
            snapd cannot resolve a plug from the snap name alone.
        slot: The slot to connect to. May be given as:

            - ``None`` (the default) to auto-resolve both the slot's snap and name. Shorthand
              for ``('', '')``. snapd searches for a system snap and matching interface slot
              for the plug. Raises if the chosen snap has no matching slot, or more than one.
            - a bare snap name, to auto-resolve the matching slot on that snap (again raising
              if that snap has no matching slot, or more than one). Shorthand for ``(snap, '')``.
            - a ``(snap, slot)`` pair, to name the slot explicitly. Either part may be an
              empty string to have snapd resolve it as above (an empty snap resolves to the
              system snap; an empty slot resolves to the matching slot on the given snap).

    Raises:
        NotFoundError: if the plug snap or slot snap is not installed (the plug snap is checked
            first). Not raised for the ``system``/``core`` slot aliases, which snapd serves
            without the core snap.
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
    # NOTE: The API requires single-element plugs and slots lists (many-to-many is a 501),
    # and rejects an empty plug snap or plug name ('plug snap name is empty' / 'plug name is
    # empty'), so a bare snap name is only meaningful for the slot side. The slot, by contrast,
    # is fully resolvable: an empty snap picks the system snap, and an empty slot name picks the
    # single matching slot on that snap. See interfaces/repo.go:ResolveConnect.
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
        _raise_not_installed_snap(plug_snap, slot_snap)
        raise


def disconnect(
    plug: tuple[str, str] | None = None,
    slot: tuple[str, str] | None = None,
    *,
    forget: bool = False,
) -> None:
    """Disconnect a plug from a slot.

    At least one of ``plug`` or ``slot`` should name something to disconnect. Each is a
    ``(snap, name)`` pair; unlike :func:`connect`, a bare snap name is not accepted on either
    side, because snapd requires the plug or slot name to identify what to disconnect. An
    ``APIError`` is raised if neither side is specified or if either side is partially specified.

    An empty snap on either side means the system snap (mirroring :func:`connect`'s slot): for
    example ``('', 'mount-observe')`` refers to ``mount-observe`` on ``snapd``/``core``.

    Three forms are supported:

    - ``plug`` only: disconnect everything connected to that plug. No-op if nothing is connected.
    - ``slot`` only: disconnect everything connected to that slot. No-op if nothing is connected.
    - both ``plug`` and ``slot``: disconnect that specific plug-slot connection. An ``APIError``
      is raised if they are not connected.

    Args:
        plug: The plug side, as a ``(snap, plug)`` pair. Omit to disconnect by slot only.
        slot: The slot side, as a ``(snap, slot)`` pair. Omit to disconnect by plug only.
        forget: If ``True``, also forget any manual connection preference, so the interface
            is not automatically reconnected on the next refresh.

    Raises:
        NotFoundError: if a named snap is not installed (the plug snap is checked first).
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
    # NOTE: A side is either fully empty ({'', ''}) or has a name; snapd rejects a bare snap
    # ({snap, ''}), and an all-empty request, with 'allowed forms are ...'. We let that flow
    # through as an APIError -- as connect does for its own all-empty case -- rather than
    # second-guessing snapd client-side. See overlord/ifacestate/ifacemgr.go:ResolveDisconnect.
    plug_snap, plug_name = _snap_and_name(plug)
    slot_snap, slot_name = _snap_and_name(slot)
    data: dict[str, Any] = {
        'action': 'disconnect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap, 'slot': slot_name}],
    }
    if forget:
        data['forget'] = True
    # NOTE: For a single-sided disconnect, the API raises interfaces-unchanged when nothing is
    # connected. We suppress this to make disconnect symmetric with connect (following the snap
    # CLI). A fully-specified disconnect instead raises a plain 'it is not connected' APIError,
    # which we leave to propagate (see the docstring).
    try:
        _client.post('/v2/interfaces', body=data)
    except _errors._InterfacesUnchangedError:
        pass  # Follow the snap CLI's lead and suppress this error.
    except _errors.APIError:
        # Turn snapd's empty-kind 'snap is not installed' error into a typed NotFoundError.
        _raise_not_installed_snap(plug_snap, slot_snap)
        raise
