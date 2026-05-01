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

import logging

from . import _errors, _snapd_snaps, _utils

logger = logging.getLogger(__name__)


def ensure_revision(snap: str, revision: int, *, classic: bool = False) -> bool:
    """Ensure the snap is installed at the specified revision.

    Returns:
        True if the snap was installed or updated, False otherwise.
    """
    info = _snapd_snaps.info(snap, missing_ok=True)
    if info is None:
        _snapd_snaps.install(snap, revision=revision, classic=classic)
        return True
    if info.revision != revision:
        _snapd_snaps.refresh(snap, revision=revision)
        return True
    return False


def ensure_channel(
    snap: str, channel: str | None = None, *, classic: bool = False, update: bool = True
) -> bool:
    """Ensure the snap is installed and up-to-date on the specified channel.

    The action taken depends on the current state of the snap:
    - If the snap is not installed, it will be installed on the specified channel
      (defaulting to latest/stable).
    - If the snap is installed on a different channel, it will be refreshed to the
      specified channel.
    - If the snap is already installed on the specified channel (or installed at all if no
      channel is specified), it will be refreshed only if update = ``True`` (default).

    Returns:
        True if the snap was installed or updated, False otherwise.
    """
    info = _snapd_snaps.info(snap, missing_ok=True)
    if info is None:
        _snapd_snaps.install(snap, channel=channel, classic=classic)
        return True
    if channel is not None and info.channel != _utils._normalize_channel(channel):
        _snapd_snaps.refresh(snap, channel=channel)
        return True
    if not update:
        return False
    try:
        _snapd_snaps.refresh(snap, channel=channel, strict=True)
    except _errors.SnapNoUpdatesAvailableError:
        return False
    return True


def ensure(
    snap: str, *, channel: str | None = None, revision: int | None = None, classic: bool = False
) -> bool:
    """Ensure that the specified snap is installed with the specified channel or revision.

    If neither is specified, ensure that it is installed at all, or install latest/stable if not.

    Returns:
        True if any action was taken (install or refresh), False otherwise.

    Raises:
        ValueError: if both channel and revision are specified.
        SnapError: (or a subtype) if the snap could not be installed or refreshed as requested.
    """
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    logger.debug('ensure:Querying info for snap %r', snap)
    # Install if the snap is not already installed.
    info = _snapd_snaps.info(snap, missing_ok=True)
    if info is None:
        logger.debug('ensure: Snap %r is not installed: installing ...', snap)
        _snapd_snaps.install(snap, channel=channel, revision=revision, classic=classic)
        return True
    # Refresh if the snap is installed with a different channel or revision than requested.
    different_channel = channel is not None and info.channel != _utils._normalize_channel(channel)
    different_revision = revision is not None and info.revision != revision
    if different_channel or different_revision:
        msg = 'ensure: Snap %r is installed with channel=%r and revision=%d but requested (channel=%r, revision=%r): refreshing ...'  # noqa: E501
        logger.debug(msg, snap, info.channel, info.revision, channel, revision)
        _snapd_snaps.refresh(snap, channel=channel, revision=revision)
        return True
    # Return False if no operations were performed.
    msg = 'ensure: Snap %r is already installed with classic=%s, channel=%r and revision=%d'
    logger.debug(msg, snap, info.classic, info.channel, info.revision)
    return False
