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
    """Information about an installed snap."""

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
        self._tracking = tracking
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
        """The snap's name."""
        return self._name

    @property
    def classic(self) -> bool:
        """Whether the snap is installed with classic confinement."""
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
        """The snap's revision, as a string.

        Note that locally installed snaps have revisions in the form 'x<N>'.
        """
        return self._revision

    @property
    def version(self) -> str:
        """The version of the installed software as reported by snapd."""
        return self._version

    @property
    def hold(self) -> datetime.datetime | None:
        """The date the snap is held until, or None if it is not held.

        A held snap is not automatically refreshed, but can be manually refreshed.

        For an indefinite hold, snapd reports a timestamp roughly 292 years after the hold was
        placed (Go's maximum duration), which is hopefully sufficient.
        """
        return self._hold

    def __repr__(self) -> str:
        hold = None if self.hold is None else self.hold.isoformat()
        return (
            f'{type(self).__name__}('
            f'{self.name!r}'
            f', classic={self.classic!r}'
            f', tracking={self.tracking!r}'
            f', revision={self.revision!r}'
            f', version={self.version!r}'
            f', hold={hold!r}'
            ')'
        )


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
        ValueError: if the snap name is empty, blank, or is not a single path segment.
        NotInstalledError: if the snap is not installed.
        BadResponseError: if snapd's description of the snap isn't one we can read.
        Error: (or a subtype) if the information could not be retrieved for another reason.
    """
    try:
        info_dict = _client.get(f'/v2/snaps/{_utils.snap_path_segment(snap)}')
    except _errors._NotFoundError as e:
        # snap-not-found -> NotInstalledError: This queries local state only.
        raise _errors.NotInstalledError._from(e) from None
    if not isinstance(info_dict, dict):
        raise _errors.BadResponseError(
            message=f'Unexpected response type {type(info_dict).__name__!r} for snap {snap!r}, expected a "dict"',  # noqa: E501
            response=info_dict,
        )
    info_dict = typing.cast('dict[str, str]', info_dict)
    try:
        return InstalledInfo._from_dict(info_dict)
    except (KeyError, TypeError, ValueError) as e:
        # A field we require is missing, or holds something we can't parse. Reported rather than
        # asserted, so that the documented contract -- every failure is an Error -- holds here too.
        raise _errors.BadResponseError(
            message=f"Could not read snapd's description of snap {snap!r}: {e!r}",
            response=info_dict,
        ) from None


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
        classic: Permission to install a snap that requires classic confinement.
            If a snap requires classic confinement and ``classic`` is not true,
            a :class:`NeedsClassicError` is raised.

    Returns:
        A truthy value if the snap was installed, or a falsy value if it was already installed.
        Not guaranteed to be an actual :class:`bool`. Note that a falsy result doesn't mean the
        snap is installed on the requested channel or revision, just that it was already installed
        at all.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment.
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
    try:
        _client.post(path, body=data)
    except _errors._AlreadyInstalledError:
        # NOTE: Following the CLI, don't error if the snap is already installed.
        # This includes the case where the snap is installed on a different channel/revision.
        return False
    except _errors._NotFoundError as e:
        # snap-not-found -> NotInStoreError: The snap not being installed wouldn't be an error,
        # so 'not found' here means the store has no snap by that name.
        raise _errors.NotInStoreError._from(e) from None
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
        ValueError: if the snap name is empty, blank, or is not a single path segment.
        ChangeError: if the removal fails after starting (for example, a remove hook errors).
        Error: (or a subtype) if the snap could not be removed as requested.
    """
    path = f'/v2/snaps/{_utils.snap_path_segment(snap)}'
    data: dict[str, Any] = {'action': 'remove'}
    if purge:
        data['purge'] = True
    # NOTE: Unlike the API, the CLI doesn't error if the snap isn't installed (just prints a msg).
    try:
        _client.post(path, body=data)
    except _errors._NotFoundError:
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
        classic: Permission to refresh to a revision that requires classic confinement from
            a revision that does not.

    Returns:
        A truthy value if the snap was refreshed, or a falsy value if no updates were available.
        Not guaranteed to be an actual :class:`bool`. Note that snapd always refreshes when a
        revision is specified, even if that revision is already installed.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment.
        NotInstalledError: if the snap is not installed.
        NotInStoreError: if the snap is installed but the store no longer offers it.
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
        # NOTE: snapd sends an error with no 'kind' if the snap isn't installed.
        # We convert to NotInstalledError here if the snap isn't installed.
        if error := _utils.check_installed(snap):
            raise error from None
        # Otherwise, not-found-error -> NotInStoreError.
        if type(e) is _errors._NotFoundError:  # 'is' to avoid matching subclasses.
            raise _errors.NotInStoreError._from(e) from None
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
        ValueError: if the snap name is empty, blank, or is not a single path segment.
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
    try:
        _client.post(path, body=data)
    except _errors.APIError:
        # NOTE: snapd sends an error with no 'kind' if the snap isn't installed.
        if error := _utils.check_installed(snap):
            raise error from None
        raise


def unhold(snap: str) -> None:
    """Unhold a snap to allow it to be refreshed.

    Does not raise if the snap is not held, or if it is not installed (an absent snap is not held).

    Args:
        snap: The name of the snap to unhold.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment.
        ChangeError: If the unhold change fails after starting.
    """
    # NOTE: Neither the API nor CLI error if the snap isn't installed or held.
    _client.post(f'/v2/snaps/{_utils.snap_path_segment(snap)}', body={'action': 'unhold'})
