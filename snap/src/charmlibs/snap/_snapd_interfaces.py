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


def connect(
    plug_snap: str, plug: str, slot_snap: str | None = None, slot: str | None = None, /
) -> None:
    """Connect a snap and plug, to a target snap and slot.

    Connecting an already-connected plug and slot succeeds silently.

    Args:
        plug_snap: The name of the snap providing the plug.
        plug: The name of the plug on ``plug_snap``.
        slot_snap: The name of the snap providing the slot. If omitted, snapd auto-resolves
            the slot, typically to the system snap (``snapd`` or ``core``).
        slot: The name of the slot on ``slot_snap``. If omitted, snapd auto-resolves it.

    Raises:
        APIError: if the plug snap or slot snap is not installed, or the named plug or slot
            does not exist. The error has an empty ``kind``; inspect ``message`` for details.
        ChangeError: if the connection fails after starting (for example, an interface hook
            errors).
    """
    data = {
        'action': 'connect',
        'plugs': [{'snap': plug_snap, 'plug': plug}],
        'slots': [{'snap': slot_snap or '', 'slot': slot or ''}],
    }
    _client.post('/v2/interfaces', body=data)


def disconnect(
    plug_or_slot_snap: str,
    plug_or_slot: str,
    slot_snap: str | None = None,
    slot: str | None = None,
    /,
    *,
    forget: bool = False,
) -> None:
    """Disconnect a plug from a slot.

    May be called in two forms:

    - ``(snap, plug_or_slot)`` disconnects everything connected to the named plug or slot
      on ``snap``.
    - ``(plug_snap, plug, slot_snap[, slot])`` disconnects the plug from the slot. ``slot``
      may be omitted to disconnect the plug from any slot on ``slot_snap``.

    Disconnecting a plug and slot that are not connected is a no-op and does not raise
    (the underlying ``interfaces-unchanged`` error is suppressed, mirroring the snap CLI).

    Args:
        plug_or_slot_snap: The snap providing the plug (explicit form) or the snap providing
            the plug or slot to disconnect (two-argument form).
        plug_or_slot: The plug on ``plug_or_slot_snap`` (explicit form) or the plug or slot
            name to disconnect (two-argument form).
        slot_snap: The snap providing the slot. Omit for the two-argument form.
        slot: The slot on ``slot_snap``. May be omitted to match any slot on ``slot_snap``.
        forget: If ``True``, also forget any manual connection preference, so the interface
            is not automatically reconnected on the next refresh.

    Raises:
        APIError: if a named snap is not installed, or the named plug or slot does not exist.
            The error has an empty ``kind``; inspect ``message`` for details.
        ChangeError: if the disconnection fails after starting (for example, an interface hook
            errors).
    """
    data: dict[str, Any] = {'action': 'disconnect'}
    if slot_snap is None:
        assert slot is None
        # Called with 2 arguments, treat as `snap disconnect <snap>:<slot>`.
        data['plugs'] = [{'snap': '', 'plug': ''}]
        data['slots'] = [{'snap': plug_or_slot_snap, 'slot': plug_or_slot}]
    else:
        # Called with 3 or 4 arguments, treat as `snap disconnect <snap>:<plug> <snap>:<slot>`.
        data['plugs'] = [{'snap': plug_or_slot_snap, 'plug': plug_or_slot}]
        data['slots'] = [{'snap': slot_snap, 'slot': slot or ''}]
    if forget:
        data['forget'] = True
    # NOTE: Unlike connect, the API raises interfaces-unchanged if already disconnected.
    # We suppress this to make disconnect symmetric with connect (following the snap CLI).
    try:
        _client.post('/v2/interfaces', body=data)
    except _errors._InterfacesUnchangedError:
        pass  # Follow the snap CLI's lead and suppress this error.
