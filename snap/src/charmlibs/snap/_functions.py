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


def ensure(
    snap: str,
    channel: str | None = None,
    *,
    revision: int | str | None = None,
    classic: bool = False,
    update: bool = True,
) -> object:
    """Ensure the snap is installed, on the specified channel and revision.

    The action taken depends on the current state of the snap:

    - If the snap is not installed, it will be installed on the specified channel and
      revision (defaulting to the latest revision on ``latest/stable``).
    - If the snap is installed on a different channel or revision, it will be refreshed to
      the specified channel and revision.
    - If the snap already matches what was specified, it will be refreshed only if a
      revision wasn't specified and update = ``True`` (default).

    Args:
        snap: The name of the snap to install or update.
        channel: The channel to track, for example ``latest/edge``. If ``None`` (default),
            the snap is installed from ``latest/stable`` when not already installed, and an
            already-installed snap's channel is left unchanged.

            A channel that starts with a risk inherits the track an installed snap is on, so
            ensuring ``edge`` for a snap that tracks ``3.6/stable`` gives ``3.6/edge``.
        revision: The revision to install, as an int or string. If ``None`` (default), the
            latest revision on the channel is used.

            A revision isn't a pin: the next refresh of this snap, including an automatic
            one, will move it to the current revision of the channel it tracks. Use
            :func:`hold` to prevent automatic refreshes. Pass ``channel`` as well as
            ``revision`` to control which channel the snap tracks -- otherwise a newly
            installed snap tracks ``latest/stable``, whichever channel the revision was
            found on.
        classic: Permission to install or refresh a revision that requires classic confinement,
            which snapd refuses to do without it. Confinement is a property of the revision, not
            something this selects, so it is never on its own a reason to refresh a snap that is
            already installed.
        update: If ``True`` (default), refresh the snap when it is already installed on the
            requested channel. If ``False``, leave an already-correct snap untouched.

            Ignored when ``revision`` is specified, since that fully determines which
            revision the snap should be on, leaving nothing to update to.

    Returns:
        A truthy value if the snap was installed or updated, or a falsy value otherwise.
        Not guaranteed to be an actual :class:`bool`.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment.
        NotInStoreError: If the store has no snap by that name.
        NotInstalledError: If the snap is removed between the check for whether it is installed
            and the refresh.
        RevisionNotAvailableError: If the revision is not available on any channel.
        NeedsClassicError: If the snap requires ``classic=True``.
        ChannelNotAvailableError: If the channel is invalid or unavailable, or if the revision
            is not available on it.
        ChangeError: If the install or refresh fails after starting (for example, a hook errors).
        Error: (or a subtype) if the snap could not be installed or refreshed for another reason.
    """
    info = _installed_info(snap)
    if info is None:  # Not installed.
        _snapd_snaps.install(snap, channel=channel, revision=revision, classic=classic)
        return True
    # Compare against the channel snapd would end up tracking, not the channel as requested,
    # so that an equivalent way of naming the tracked channel isn't seen as a change.
    on_channel = _utils.resolve_channel(channel or '', info.tracking) == info.tracking
    on_revision = revision is None or info.revision == str(revision)
    if not on_channel or not on_revision:
        _snapd_snaps.refresh(snap, channel=channel, revision=revision, classic=classic)
        return True
    # Already installed as specified.
    if revision is not None:
        # A revision was specified and is installed, so there's nothing to update to. Refreshing
        # would be churn: snapd runs a full refresh when a revision is specified, even if that
        # revision is already installed, and would report that it did something.
        return False
    if not update:  # User explicitly requested no update in this case.
        return False
    return _snapd_snaps.refresh(snap, channel=channel, classic=classic)


def _installed_info(snap: str) -> _snapd_snaps.InstalledInfo | None:
    """Return the snap's local state, or None if it is not installed."""
    try:
        return _snapd_snaps.list_one(snap)
    except _errors.NotInstalledError:
        return None
