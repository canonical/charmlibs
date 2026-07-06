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

"""High level helper functions that build on top of the basic snap operations."""

from . import _errors, _snapd_snaps, _utils


def ensure_revision(snap: str, revision: int | str, *, classic: bool = False) -> object:
    """Ensure the snap is installed at the specified revision.

    Args:
        snap: The name of the snap to install or update.
        revision: The revision to ensure is installed, as an int or string.
        classic: If ``True``, install the snap with classic confinement. Required for snaps
            that use classic confinement.

    Returns:
        A truthy value if the snap was installed or updated, or a falsy value otherwise.
        Not guaranteed to be an actual :class:`bool`.

    Raises:
        NotFoundError: If the snap does not exist in the store.
        RevisionNotAvailableError: If the revision does not exist.
        NeedsClassicError: If the snap requires ``classic=True``.
        ChangeError: If the install or refresh fails after starting (for example, a hook errors).
        Error: (or a subtype) if the snap could not be installed or refreshed for another reason.
    """
    info = _get_info(snap)
    if info is None:  # Not installed.
        _snapd_snaps.install(snap, revision=revision, classic=classic)
        return True
    if info.revision != str(revision):  # Installed but at different revision.
        _snapd_snaps.refresh(snap, revision=revision)
        return True
    return False  # Already installed at the requested revision.


def ensure(
    snap: str, channel: str | None = None, *, classic: bool = False, update: bool = True
) -> object:
    """Ensure the snap is installed and up-to-date on the specified channel.

    The action taken depends on the current state of the snap:

    - If the snap is not installed, it will be installed on the specified channel
      (defaulting to latest/stable).
    - If the snap is installed on a different channel, it will be refreshed to the
      specified channel.
    - If the snap is already installed on the specified channel (or installed at all if no
      channel is specified), it will be refreshed only if update = ``True`` (default).

    Args:
        snap: The name of the snap to install or update.
        channel: The channel to track, for example ``latest/edge``. If ``None`` (default),
            the snap is installed from ``latest/stable`` when not already installed, and an
            already-installed snap's channel is left unchanged.
        classic: If ``True``, install the snap with classic confinement. Required for snaps
            that use classic confinement.
        update: If ``True`` (default), refresh the snap when it is already installed on the
            requested channel. If ``False``, leave an already-correct snap untouched.

    Returns:
        A truthy value if the snap was installed or updated, or a falsy value otherwise.
        Not guaranteed to be an actual :class:`bool`.

    Raises:
        NotFoundError: If the snap does not exist in the store.
        NeedsClassicError: If the snap requires ``classic=True``.
        ChannelNotAvailableError: If the channel is invalid or unavailable.
        ChangeError: If the install or refresh fails after starting (for example, a hook errors).
        Error: (or a subtype) if the snap could not be installed or refreshed for another reason.
    """
    info = _get_info(snap)
    if info is None:  # Not installed.
        _snapd_snaps.install(snap, channel=channel, classic=classic)
        return True
    if channel and info.channel != _utils.normalize_channel(channel):
        # Installed but on a different channel.
        _snapd_snaps.refresh(snap, channel=channel)
        return True
    # Already installed on the requested channel (or any channel if none was specified).
    if not update:  # User explicitly requested no update in this case.
        return False
    return _snapd_snaps.refresh(snap, channel=channel)


def _get_info(snap: str) -> _snapd_snaps.Info | None:
    """Get snap info, raising an error if the snap is not installed."""
    try:
        return _snapd_snaps.info(snap)
    except _errors.NotFoundError:
        return None
