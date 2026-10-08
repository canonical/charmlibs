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

from . import _errors, _snapd_conf, _snapd_snaps, _utils


def ensure_installed(
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
        classic: Permission to install or refresh a revision that requires classic confinement.
            If a snap revision requires classic confinement and ``classic`` is not true,
            a :class:`NeedsClassicError` is raised.
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


def ensure_vitality_hint(snap: str) -> object:
    """Ensure the snap is in the system's ``resilience.vitality-hint`` list.

    The vitality hint is an ordered list of snaps whose services the kernel's out-of-memory
    (OOM) killer should spare, most important first. This function appends the snap to the end of
    the list if it is not already present.

    You can call this function before the snap is installed, and snapd will apply the hint when
    the snap is installed. If the snap is already installed, snapd rewrites the snap's
    service units straight away, and starts any services that are enabled but stopped.
    A running service keeps its current score until it next starts, so use :func:`restart`
    if you want the hint applied immediately.

    This works by setting each service's ``OOMScoreAdjust``, which ranges from -1000
    (special: never killed) to 1000, with a default of 0. Lower values mean more protection.
    When the system runs out of memory, the kernel kills the process with the highest score based
    on its share of memory (1000 * 0.1 -> 100, 1000 * 0.5 -> 500) plus its ``OOMScoreAdjust``.
    snapd sets ``OOMScoreAdjust`` to ``-900`` plus the snap's position in the list: ``-899``
    for the first snap, ``-898`` for the second, and so on, up to ``-800`` for the 100th.
    Unlisted snaps' services keep the default of ``0``, like most other processes.
    So a listed snap's service (-899 - -800) can only be killed ahead of an unlisted process (0)
    if it uses memory on the order of 80-90% of the system's total memory.
    Between listed snaps, memory use differences are the more significant factor.

    Args:
        snap: The name of the snap to add to the list. A snap instance name, such as
            ``foo_bar``, may be used to target a parallel install.

    Returns:
        A truthy value if the snap was added to the list, or a falsy value if it was already
        listed. Not guaranteed to be an actual :class:`bool`.

    Raises:
        ValueError: if the snap name is empty, blank, contains a comma, has leading or
            trailing whitespace, or is "snapd" (whose services are always at ``-900``).
        ChangeError: if snapd rejects the updated list: if the snap name is not a valid snap
            name, or if the list would contain too many snaps (snapd's current limit is 100).
        BadResponseError: if snapd returns a non-string value for the vitality hint.
    """
    _utils.raise_if_not_comma_list_safe(snap, label='snap name')
    if snap == 'snapd':
        raise ValueError('snap name cannot be "snapd"')
    vitality_hint = 'resilience.vitality-hint'
    try:
        current = _snapd_conf.get_one('system', vitality_hint)
    except _errors.OptionNotFoundError:
        current = ''
    if not isinstance(current, str):
        # NOTE: This should never happen as snapd rejects malformed values for this option.
        msg = f'Unexpected config type {type(current).__name__!r} for {vitality_hint!r} (expected a "str")'  # noqa: E501
        raise _errors.BadResponseError(msg, response=current)
    hints = current.split(',') if current else []  # Treat '' as an empty list.
    if snap in hints:
        return False
    _snapd_conf.set('system', {vitality_hint: ','.join([*hints, snap])})
    return True


def _installed_info(snap: str) -> _snapd_snaps.InstalledInfo | None:
    """Return the snap's local state, or None if it is not installed."""
    try:
        return _snapd_snaps.list_one(snap)
    except _errors.NotInstalledError:
        return None
