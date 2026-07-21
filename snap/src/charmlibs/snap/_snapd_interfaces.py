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

from . import _client, _errors

# /v2/interfaces


def connect(plug: tuple[str, str], slot: tuple[str, str] | str | None = None) -> None:
    """Connect a snap's plug to a slot.

    Connecting an already-connected plug and slot succeeds silently.

    Args:
        plug: The plug to connect, as a ``(snap, plug)`` pair. Both parts are required:
            snapd cannot resolve a plug from the snap name alone.
        slot: The slot to connect to. May be given as:

            - ``None`` (the default) to let snapd auto-resolve the slot, typically to the
              system snap (``snapd`` or ``core``), matching the plug's interface.
            - a bare snap name, to auto-resolve the matching slot on that snap.
            - a ``(snap, slot)`` pair, to name the slot explicitly. Either part may be an
              empty string to have snapd resolve it (an empty snap resolves to the system
              snap; an empty slot resolves to the matching slot on the given snap).

    Raises:
        APIError: if the plug snap or slot snap is not installed, the named plug or slot does
            not exist, the plug and slot interfaces do not match, or the slot cannot be
            resolved unambiguously. The error has an empty ``kind``; inspect ``message``.
        ChangeError: if the connection fails after starting (for example, an interface hook
            errors).

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
    plug_snap, plug_name = plug  # Unpacking rejects a bare string plug with a clear ValueError.
    if slot is None:
        slot_snap, slot_name = '', ''
    else:
        # A bare snap name means 'resolve the matching slot on this snap'.
        slot_snap, slot_name = (slot, None) if isinstance(slot, str) else slot
    data = {
        'action': 'connect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap or '', 'slot': slot_name or ''}],
    }
    _client.post('/v2/interfaces', body=data)


def disconnect(
    plug: tuple[str, str] | None = None,
    slot: tuple[str, str] | None = None,
    *,
    forget: bool = False,
) -> None:
    """Disconnect a plug from a slot.

    At least one of ``plug`` or ``slot`` must be given. Each is a ``(snap, name)`` pair;
    unlike :func:`connect`, a bare snap name is not accepted on either side, because snapd
    requires the plug or slot name to identify what to disconnect.

    Three forms are supported:

    - ``plug`` only: disconnect everything connected to that plug.
    - ``slot`` only: disconnect everything connected to that slot.
    - both ``plug`` and ``slot``: disconnect that specific plug-slot connection.

    The two single-sided forms are a no-op when nothing is connected: snapd reports
    ``interfaces-unchanged``, which is suppressed here (mirroring the snap CLI). The
    fully-specified form is **not** symmetric: if the named plug and slot are not connected,
    snapd raises ``APIError`` (``'... it is not connected'``) rather than reporting
    ``interfaces-unchanged``, and that error is not suppressed.

    Args:
        plug: The plug side, as a ``(snap, plug)`` pair. Omit to disconnect by slot only.
        slot: The slot side, as a ``(snap, slot)`` pair. Omit to disconnect by plug only.
        forget: If ``True``, also forget any manual connection preference, so the interface
            is not automatically reconnected on the next refresh.

    Raises:
        ValueError: if neither ``plug`` nor ``slot`` is given.
        APIError: if a named snap is not installed, the named plug or slot does not exist, or
            the fully-specified plug and slot are not connected. The error has an empty
            ``kind``; inspect ``message`` for details.
        ChangeError: if the disconnection fails after starting (for example, an interface hook
            errors).

    ::

        # Disconnect everything from a plug (no-op if nothing is connected).
        disconnect(('mysnap', 'home'))
        # Disconnect everything from a slot.
        disconnect(slot=('other-snap', 'content-slot'))
        # Disconnect one specific connection (raises if not connected).
        disconnect(('mysnap', 'content'), ('other-snap', 'content-slot'))
    """
    if plug is None and slot is None:
        raise ValueError('at least one of plug or slot must be given')
    # NOTE: A side is either fully empty ({'', ''}) or has a name; snapd rejects a bare snap
    # ({snap, ''}) with 'allowed forms are ...'. Unpacking rejects a bare string with a clear
    # ValueError. See overlord/ifacestate/ifacemgr.go:ResolveDisconnect.
    plug_snap, plug_name = ('', '') if plug is None else plug
    slot_snap, slot_name = ('', '') if slot is None else slot
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
