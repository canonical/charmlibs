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


class InstalledInfo:
    def __init__(
        self,
        name: str,
        classic: bool,
        tracking: str,
        revision: int | str,
        version: str,
        hold: datetime.datetime | str | None,
    ):
        self._name = name
        self._classic = classic
        self._tracking = _utils.normalize_channel(tracking)
        self._revision = str(revision)
        self._version = version
        self._hold = _utils.parse_timestamp(hold) if isinstance(hold, str) else hold

    @classmethod
    def _from_dict(cls, info_dict: dict[str, str]) -> Self:
        return cls(
            name=info_dict['name'],
            # NOTE: 'tracking-channel' is the channel the snap follows, which is what `snap list`
            # reports and what a refresh without a channel follows. It differs from 'channel',
            # the channel the installed revision was sourced from: installing a revision without
            # a channel tracks latest/stable but sources the revision from wherever it lives.
            # Absent entirely for a snap installed from a local file.
            tracking=info_dict.get('tracking-channel', ''),
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
    def tracking(self) -> str:
        """The channel the snap tracks, for example ``latest/stable``.

        This is the channel a refresh follows, shown as ``Tracking`` by ``snap list``. It isn't
        necessarily the channel the installed revision came from: installing a specific revision
        without a channel tracks ``latest/stable``, whichever channel that revision was found on.

        Empty for a snap installed from a local file, which tracks no channel.
        """
        return self._tracking

    @property
    def revision(self) -> str:
        return self._revision

    @property
    def version(self) -> str:
        return self._version

    @property
    def hold(self) -> datetime.datetime | None:
        return self._hold


def list_one(snap: str) -> InstalledInfo:
    """Get information about a single installed snap.

    This function implements the semantics of the ``snap list`` command, restricted to a single
    snap: it reports the local state of an installed snap and never queries the snap store.
    It is named for that command rather than ``snap info``, which reports what the store offers
    for a snap -- the channels available and their revisions -- and is not implemented here.

    Args:
        snap: the name of the snap.

    Returns:
        An :class:`InstalledInfo` object with information about the snap.

    Raises:
        ValueError: if the snap name is empty or is not a single path segment.
        NotInstalledError: if the snap is not installed.
        Error: (or a subtype) if the information could not be retrieved for another reason.
    """
    try:
        info_dict = _client.get(f'/v2/snaps/{_utils.snap_path_segment(snap)}')
    except _errors.NotFoundError as e:
        # This endpoint reports local state only, so not-found can only mean not installed.
        raise _errors.NotInstalledError._narrowed(e) from None
    assert isinstance(info_dict, dict)
    info_dict = typing.cast('dict[str, str]', info_dict)
    return InstalledInfo._from_dict(info_dict)


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
        channel: The channel to track, for example ``latest/edge``. If ``revision`` is also
            given, the revision must be available on this channel. If neither is given, snapd
            installs from ``latest/stable``.
        revision: The revision to install, as an int or string. Installing a revision doesn't
            pin the snap to it -- the next refresh will move the snap to the current revision
            of the channel it tracks. Use :func:`hold` to prevent automatic refreshes.

            Without ``channel``, snapd finds the revision on whichever channel it's available
            on, but the snap tracks ``latest/stable`` regardless, so a later refresh may move
            the snap to a different channel's revision. Pass ``channel`` as well to control
            which channel the snap tracks.
        classic: Grants permission to install a revision that requires classic confinement,
            which snapd refuses to install without it. It does not select the confinement:
            that is a property of the revision, declared in the snap itself. Passing ``True``
            for a revision that doesn't require classic confinement is silently ignored.

    Returns:
        A truthy value if the snap was installed, or a falsy value if it was already installed.
        Not guaranteed to be an actual :class:`bool`.

    Raises:
        ValueError: if the snap name is empty or is not a single path segment.
        NotInStoreError: if the store has no snap by that name.
        RevisionNotAvailableError: if the specified revision is not available on any channel.
        ChannelNotAvailableError: if the specified channel is not available, or if the specified
            revision is not available on it.
        NeedsClassicError: if the snap requires classic confinement and ``classic`` is not set.
        ChangeError: if the install fails after starting (for example, an install hook errors).
        Error: (or a subtype) if the snap could not be installed for another reason.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}'
    # NOTE: channel and revision aren't mutually exclusive. Snapd installs the revision and
    # tracks the channel, erroring if the revision isn't available on that channel. The one
    # combination snapd does reject is a revision with a cohort key, which this library doesn't
    # support yet: adding cohort support means adding overloads and a check for it, here and in
    # refresh, rather than reinstating them for channel and revision.
    data: dict[str, Any] = {'action': 'install'}
    if channel:
        data['channel'] = channel
    # Sent whenever it isn't None, so that an invalid revision is reported by snapd rather than
    # silently dropped. Snap revisions are positive, or 'xN' for a snap installed from a file.
    if revision is not None:
        data['revision'] = str(revision)
    if classic:
        data['classic'] = True
    # NOTE: Unlike the API, the CLI doesn't error if it's already installed (just prints a msg).
    try:
        _client.post(path, body=data)
    except _errors._AlreadyInstalledError:
        return False
    except _errors.NotFoundError as e:
        # An install only fails this way when the store has nothing by that name: whether the
        # snap is installed isn't in question, since an installed one answers already-installed.
        raise _errors.NotInStoreError._narrowed(e) from None
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
        ValueError: if the snap name is empty or is not a single path segment.
        ChangeError: if the removal fails after starting (for example, a remove hook errors).
        Error: (or a subtype) if the snap could not be removed as requested.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}'
    data: dict[str, Any] = {'action': 'remove'}
    if purge:
        data['purge'] = True
    # NOTE: Unlike the API, the CLI doesn't error if the snap isn't installed -- it prints a
    # message and exits 0 -- so an absent snap is a falsy result here rather than an error.
    try:
        _client.post(path, body=data)
    except _errors.NotFoundError:
        # Either sense means the snap isn't on the system to remove, so there is nothing to
        # report: snapd sends the unambiguous 'snap-not-installed' kind, and the base is caught
        # too so that no unnarrowed error can escape a function that reports absence as falsy.
        return False
    return True


def refresh(
    snap: str,
    channel: str | None = None,
    *,
    revision: int | str | None = None,
    classic: bool = False,
) -> object:
    """Refresh a snap.

    Args:
        snap: The name of the snap to refresh.
        channel: The channel to track, for example ``latest/edge``. If ``revision`` is also
            given, the revision must be available on this channel. If neither is given, the
            snap is refreshed on its current channel.

            A channel that starts with a risk inherits the track the snap is on, so refreshing
            a snap that tracks ``3.6/stable`` to ``edge`` gives ``3.6/edge``.
        revision: The revision to refresh to, as an int or string. Refreshing to a revision
            doesn't pin the snap to it -- the next refresh will move the snap to the current
            revision of the channel it tracks. Use :func:`hold` to prevent automatic refreshes.

            Without ``channel``, the snap keeps tracking its current channel, even if the
            revision was found on another one.
        classic: Grants permission to refresh to a revision that requires classic confinement.
            Only needed when the installed revision doesn't require classic confinement and the
            target revision does: an already classic-confined snap keeps classic confinement
            without it, and a revision that doesn't require it silently ignores it. Confinement
            is a property of the revision, declared in the snap, not something this selects.

    Returns:
        A truthy value if the snap was refreshed, or a falsy value if no updates were available.
        Not guaranteed to be an actual :class:`bool`. Note that snapd always refreshes when a
        revision is specified, even if that revision is already installed.

    Raises:
        ValueError: if the snap name is empty or is not a single path segment.
        NotInstalledError: if the snap is not installed.
        NotInStoreError: if the snap is installed but the store no longer offers it. A refresh
            needs both, so it is the one function where either can be what's missing.
        RevisionNotAvailableError: if the specified revision is not available on any channel.
        ChannelNotAvailableError: if the specified channel is not available, or if the specified
            revision is not available on it.
        NeedsClassicError: if the target revision requires classic confinement, the installed
            revision does not, and ``classic`` is not set.
        ChangeError: if the refresh fails after starting (for example, a refresh hook errors).
        Error: (or a subtype) if the snap could not be refreshed for another reason.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}'
    data: dict[str, Any] = {'action': 'refresh'}
    if channel:
        data['channel'] = channel
    # Sent whenever it isn't None -- see the note in install().
    if revision is not None:
        data['revision'] = str(revision)
    if classic:
        data['classic'] = True
    # NOTE: Unlike the API, the CLI doesn't error if there are no updates (just prints a msg).
    try:
        _client.post(path, body=data)
    except _errors._NoUpdatesAvailableError:
        return False
    except _errors.APIError as e:
        # NOTE: A refresh needs the snap installed *and* still offered by the store, so it's the
        # one operation where both senses of NotFoundError are reachable -- and snapd tells them
        # apart badly. Not installed comes back with no 'kind' at all; withdrawn from the store
        # comes back as the same ambiguous 'snap-not-found' an install gets. So we probe
        # /v2/snaps/{snap}: absent means not installed, present means the store is what's
        # missing. Any other failure is re-raised unchanged.
        if error := _utils.check_installed(snap):
            raise error from None
        if type(e) is _errors.NotFoundError:
            raise _errors.NotInStoreError._narrowed(e) from None
        raise
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
        ValueError: if the snap name is empty or is not a single path segment.
        NotInstalledError: If the snap is not installed.
        ChangeError: If the hold change fails after starting.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}'
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
    # NOTE: As for refresh, snapd reports holding a snap that isn't installed as an error with no
    # 'kind', so we probe /v2/snaps/{snap} to raise NotFoundError. The probe runs on failure only,
    # so a successful hold doesn't pay for a second request.
    try:
        _client.post(path, body=data)
    except _errors.APIError:
        if error := _utils.check_installed(snap):
            raise error from None
        raise


def unhold(snap: str) -> None:
    """Unhold a snap to allow it to be refreshed.

    Does not raise if the snap is not installed or not held, following the snap CLI. A hold does
    not survive removal of the snap, so there is never a hold left behind to clear.

    Args:
        snap: The name of the snap to unhold.

    Raises:
        ValueError: if the snap name is empty or is not a single path segment.
        ChangeError: If the unhold change fails after starting.
    """
    # NOTE: Neither the API nor CLI error if the snap isn't installed or held.
    try:
        _client.post(f'/v2/snaps/{_utils.snap_path_segment(snap)}', body={'action': 'unhold'})
    except _errors.NotFoundError as e:
        # Unholding acts on an installed snap; the store is never consulted.
        raise _errors.NotInstalledError._narrowed(e) from None
