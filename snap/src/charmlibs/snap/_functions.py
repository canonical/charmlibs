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


def ensure_revision(snap: str, revision: int, *, classic: bool = False) -> bool:
    """Ensure the snap is installed at the specified revision.

    Returns:
        True if the snap was installed or updated, False otherwise.
    """
    info = _snapd_snaps.info(snap, missing_ok=True)
    if info is None:  # Not installed.
        _snapd_snaps.install(snap, revision=revision, classic=classic)
        return True
    if info.revision != revision:  # Installed but at different revision.
        _snapd_snaps.refresh(snap, revision=revision)
        return True
    return False  # Already installed at the requested revision.


def ensure(
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
    if info is None:  # Not installed.
        _snapd_snaps.install(snap, channel=channel, classic=classic)
        return True
    if channel is not None and info.channel != _utils._normalize_channel(channel):
        # Installed but on a different channel.
        _snapd_snaps.refresh(snap, channel=channel)
        return True
    # Already installed on the requested channel (or any channel if none was specified).
    if not update:  # User explicitly requested no update in this case.
        return False
    try:  # Refresh to get the latest revision on the current channel, if possible.
        _snapd_snaps.refresh(snap, channel=channel, strict=True)
        return True
    except _errors.SnapNoUpdatesAvailableError:
        return False  # No updates available, so no changes were made.
