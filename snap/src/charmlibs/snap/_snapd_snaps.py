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

import datetime
import logging
import typing
from typing import Any

from . import _client, _errors, _utils

if typing.TYPE_CHECKING:
    from typing_extensions import Self


logger = logging.getLogger(__name__)

# /v2/snaps/{snap}


class Info:
    def __init__(
        self,
        name: str,
        classic: bool,
        channel: str,
        revision: int | str,
        version: str,
        hold: datetime.datetime | str | None,
    ):
        self._name = name
        self._classic = classic
        self._channel = _utils.normalize_channel(channel)
        self._revision = str(revision)
        self._version = version
        self._hold = _utils.parse_timestamp(hold) if isinstance(hold, str) else hold

    @classmethod
    def _from_dict(cls, info_dict: dict[str, str]) -> Self:
        return cls(
            name=info_dict['name'],
            channel=info_dict['channel'],
            revision=info_dict['revision'],
            version=info_dict['version'],
            classic=info_dict['confinement'] == 'classic',
            hold=info_dict.get('hold'),
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def classic(self) -> bool:
        return self._classic

    @property
    def channel(self) -> str:
        return self._channel

    @property
    def revision(self) -> str:
        return self._revision

    @property
    def version(self) -> str:
        return self._version

    @property
    def hold(self) -> datetime.datetime | None:
        return self._hold


def info(snap: str) -> Info:
    """Get information about an installed snap.

    This function implements the semantics of the `snap list` command,
    restricted to a single snap.

    Args:
        snap: the name of the snap.

    Returns:
        An Info object with information about the snap.

    Raises:
        NotFoundError: if the snap is not installed.
        Error: (or a subtype) if the information could not be retrieved for another reason.
    """
    info_dict = _client.get(f'/v2/snaps/{snap}')
    assert isinstance(info_dict, dict)
    info_dict = typing.cast('dict[str, str]', info_dict)
    return Info._from_dict(info_dict)


@typing.overload
def install(
    snap: str, *, channel: str, revision: None = None, classic: bool = False
) -> object: ...
@typing.overload
def install(
    snap: str, *, channel: None = None, revision: int | str, classic: bool = False
) -> object: ...
@typing.overload
def install(
    snap: str, *, channel: None = None, revision: None = None, classic: bool = False
) -> object: ...
def install(
    snap: str,
    *,
    channel: str | None = None,
    revision: int | str | None = None,
    classic: bool = False,
) -> object:
    """Install a snap.

    Args:
        snap: The name of the snap to install.
        channel: The channel to install from, for example ``latest/edge``. Mutually exclusive
            with ``revision``. If neither is given, snapd installs from ``latest/stable``.
        revision: The revision to install, as an int or string. Mutually exclusive with
            ``channel``.
        classic: If ``True``, install the snap with classic confinement. Required for snaps
            that use classic confinement.

    Returns:
        A truthy value if the snap was installed, or a falsy value if it was already installed.
        Not guaranteed to be an actual :class:`bool`.

    Raises:
        ValueError: if both channel and revision are specified.
        NotFoundError: if the snap does not exist in the store.
        RevisionNotAvailableError: if the specified revision is not available.
        ChannelNotAvailableError: if the specified channel is not available.
        NeedsClassicError: if the snap requires classic confinement and ``classic`` is not set.
        ChangeError: if the install fails after starting (for example, an install hook errors).
        Error: (or a subtype) if the snap could not be installed for another reason.
    """
    if channel is not None and revision is not None:
        # NOTE: Revision silently takes precedence over channel in the snapd API.
        # The CLI instead returns an error if the specified revision doesn't exist on that channel.
        raise ValueError('Only one of channel or revision may be specified')
    data: dict[str, Any] = {'action': 'install'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    if classic:
        data['classic'] = True
    # NOTE: Unlike the API, the CLI doesn't error if it's already installed (just prints a msg).
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors._AlreadyInstalledError:
        return False
    return True


def remove(snap: str, *, purge: bool = False) -> object:
    """Remove a snap.

    Args:
        snap: The name of the snap to remove.
        purge: If True, remove the snap without saving a snapshot of its data.

    Returns:
        A truthy value if the snap was removed, or a falsy value if it was not installed.
        Not guaranteed to be an actual :class:`bool`.

    Raises:
        ChangeError: if the removal fails after starting (for example, a remove hook errors).
        Error: (or a subtype) if the snap could not be removed as requested.
    """
    data: dict[str, Any] = {'action': 'remove'}
    if purge:
        data['purge'] = True
    # NOTE: Unlike the API, the CLI doesn't error if the snap isn't installed (just prints a msg).
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors.NotInstalledError:
        return False
    return True


@typing.overload
def refresh(snap: str, channel: str, *, revision: None = None) -> object: ...
@typing.overload
def refresh(snap: str, channel: None = None, *, revision: int | str) -> object: ...
@typing.overload
def refresh(snap: str, channel: None = None, *, revision: None = None) -> object: ...
def refresh(
    snap: str,
    channel: str | None = None,
    *,
    revision: int | str | None = None,
) -> object:
    """Refresh a snap.

    Args:
        snap: The name of the snap to refresh.
        channel: The channel to refresh to, for example ``latest/edge``. Mutually exclusive
            with ``revision``. If neither is given, the snap is refreshed on its current channel.
        revision: The revision to refresh to, as an int or string. Mutually exclusive with
            ``channel``.

    Returns:
        A truthy value if the snap was refreshed, or a falsy value if no updates were available.
        Not guaranteed to be an actual :class:`bool`.

    Raises:
        ValueError: if both channel and revision are specified.
        RevisionNotAvailableError: if the specified revision is not available.
        ChannelNotAvailableError: if the specified channel is not available.
        ChangeError: if the refresh fails after starting (for example, a refresh hook errors).
        Error: (or a subtype) if the snap could not be refreshed for another reason.
    """
    if channel is not None and revision is not None:
        # NOTE: Revision silently takes precedence over channel in the snapd API.
        # The CLI instead returns an error if the specified revision doesn't exist on that channel.
        raise ValueError('Only one of channel or revision may be specified')
    data = {'action': 'refresh'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    # NOTE: Unlike the API, the CLI doesn't error if there are no updates (just prints a msg).
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors._NoUpdatesAvailableError:
        return False
    return True


def hold(snap: str, duration: datetime.timedelta | int | float | None = None) -> None:
    """Hold a snap to prevent it from being automatically refreshed.

    Does not prevent manual refreshes.

    Args:
        snap: The name of the snap to hold.
        duration: How long to hold automatic refreshes for, measured from now. May be a
            :class:`datetime.timedelta`, or a number of seconds as an int or float. If ``None``
            (default), the snap is held indefinitely.

    Raises:
        NotFoundError: If the snap is not installed.
        ChangeError: If the hold change fails after starting.
    """
    # https://forum.snapcraft.io/t/snapd-rest-api/17954
    if duration is None:
        until = 'forever'
    else:
        if isinstance(duration, datetime.timedelta):
            delta = duration
        else:
            delta = datetime.timedelta(seconds=duration)
        until = (datetime.datetime.now(datetime.timezone.utc) + delta).isoformat()
    data = {'action': 'hold', 'hold-level': 'general', 'time': until}
    # NOTE: The API returns an error with no 'kind' when holding a non-installed snap.
    # The CLI raises an error in this case, so we pre-emptively check if the snap is installed.
    info(snap)  # Raise NotFoundError if not installed.
    _client.post(f'/v2/snaps/{snap}', body=data)


def unhold(snap: str) -> None:
    """Unhold a snap to allow it to be refreshed.

    Does not raise if the snap is not installed or not held.

    Args:
        snap: The name of the snap to unhold.

    Raises:
        ChangeError: If the unhold change fails after starting.
    """
    # NOTE: Neither the API nor CLI error if the snap isn't installed or held.
    _client.post(f'/v2/snaps/{snap}', body={'action': 'unhold'})
