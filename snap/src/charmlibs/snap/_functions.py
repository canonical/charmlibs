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

from __future__ import annotations

import typing
from typing import Any

from . import _errors, _snapd_quotas, _snapd_snaps, _utils

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


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


def _installed_info(snap: str) -> _snapd_snaps.InstalledInfo | None:
    """Return the snap's local state, or None if it is not installed."""
    try:
        return _snapd_snaps.list_one(snap)
    except _errors.NotInstalledError:
        return None


def ensure_quota(
    group: str,
    snaps: str | Iterable[str] | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    *,
    services: Mapping[str, str | Iterable[str]] | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    parent: str | type[_utils.UNCHANGED] | None = _utils.UNCHANGED,
    memory: int | type[_utils.UNCHANGED] | None = _utils.UNCHANGED,
    cpu: tuple[int | None, int] | type[_utils.UNCHANGED] | None = _utils.UNCHANGED,
    cpu_set: Iterable[int] | type[_utils.UNCHANGED] | None = _utils.UNCHANGED,
    threads: int | type[_utils.UNCHANGED] | None = _utils.UNCHANGED,
) -> object:
    """Ensure a quota group exists and matches what was asked, changing it if needed.

    Every argument except ``group`` has three states:

    - **a value**: the group must have exactly this. ``ensure_quota('my-group', ['a', 'b'])``
      makes the group's snaps exactly ``a`` and ``b``, and ``memory=1024**2`` makes the
      memory limit exactly 1 MiB.
    - **the empty value**: the group must not have this. ``None`` means no limit (or no
      parent, for a top-level group), so ``memory=self.config.get('memory-limit')`` removes
      the memory limit when the config option is cleared. ``()`` means no snaps, and ``{}``
      means no services.
    - **``UNCHANGED``** (the default): leave it as it is. An argument that is left out is
      never compared, never a reason to change the group, and keeps its current value
      through any other change -- as do limits snapd reports that this function has no
      argument for, such as journal quotas. On a group that does not exist yet, "left as
      it is" means absent.

    What happens when the group doesn't match:

    - Adding snaps or services, adding a limit, raising the memory or threads limit, and
      changing the CPU limit up or down all happen **in place**, in a single change.
    - Anything else -- removing a snap or service, removing a limit, lowering memory or
      threads, changing the parent -- **re-creates** the group: it is removed and created
      again with the target membership and limits (carrying over everything left
      ``UNCHANGED``).

    Note that adding a snap to a group, and re-creating a group, restart the snap's
    services, and that a re-created group leaves its snaps unconstrained for a moment.

    This function manages one group at a time. A group that has sub-groups cannot be
    re-created: :class:`QuotaHasSubgroupsError` is raised before anything is changed, and
    the sub-groups must be removed first. Also note that snapd requires a new group to
    have at least one limit, so creating a group with only snaps (or nothing) in it is an
    :class:`APIError`.

    The intended pattern is to install every snap first (for example with
    :func:`ensure_installed`) and then call ``ensure_quota`` once, naming all of them,
    which adds them in a single change::

        ensure_installed('my-snap')
        ensure_quota('my-group', ['my-snap'], memory=self.config.get('memory-limit'))

    It is safe to call on every hook: when the group already matches, no request is made
    beyond reading the group. And after a snap is removed and installed again (which
    drops it from the group), calling ``ensure_quota`` puts it back.

    Args:
        group: The name of the quota group.
        snaps: The snaps in the group, as a single name or an iterable of names.
        services: The services in the group, as a mapping of snap name to service names:
            ``{'some-snap': ['serv1', 'serv2']}``.
        parent: The name of an existing group to nest this group under, or None for a
            top-level group.
        memory: The memory limit in bytes, or None for no memory limit. The library does
            no unit parsing.
        cpu: The CPU limit as a ``(count, percentage)`` pair -- ``(2, 50)`` is the CLI's
            ``2x50%``, and a count of None applies the percentage to every available
            core -- or None for no CPU limit. Percentage is 1 to 100.
        cpu_set: The indices of the cores the group may use, or None for no CPU set limit.
        threads: The threads limit, or None for no threads limit.

    Returns:
        A truthy value if the group was created or changed, or a falsy value if it already
        matched. Not guaranteed to be an actual :class:`bool`.

    Raises:
        ValueError: if the group name is empty, blank, or is not a single path segment; if
            a snap or service name is empty or blank; if ``memory`` or ``threads`` is zero
            or negative; if the CPU percentage is outside 1 to 100 or the CPU count is zero
            or negative; or if ``cpu_set`` is empty or contains a negative number.
        NotInstalledError: if a snap named in ``snaps`` or ``services`` is not installed.
        QuotaHasSubgroupsError: if the group must be re-created but has sub-groups.
            Nothing is changed in this case.
        APIError: for the rules left to snapd -- for example, a group name with invalid
            characters, snaps and services mixed in one group, a parent that does not
            exist, or a new group without a limit.
        ChangeError: if the operation fails after starting.
    """
    # 1. Validate every argument that was given, before any request, converting each
    # limit to the constraint entry snapd uses. A None entry means the limit must be absent.
    _utils.raise_if_not_path_segment(group, label='group name')
    snaps_list = None if snaps is _utils.UNCHANGED else _snapd_quotas._validate_snaps(snaps)
    services_dict = (
        None if services is _utils.UNCHANGED else _snapd_quotas._validate_services(services)
    )
    given: dict[str, Any] = {}
    if memory is not _utils.UNCHANGED:
        if memory is not None:
            _snapd_quotas._validate_memory(memory)
        given['memory'] = memory
    if cpu is not _utils.UNCHANGED:
        given['cpu'] = None if cpu is None else _snapd_quotas._validate_cpu(cpu)
    if cpu_set is not _utils.UNCHANGED:
        given['cpu-set'] = (
            None if cpu_set is None else {'cpus': _snapd_quotas._validate_cpu_set(cpu_set)}
        )
    if threads is not _utils.UNCHANGED:
        if threads is not None:
            _snapd_quotas._validate_threads(threads)
        given['threads'] = threads
    # 2. Read the group. A group that doesn't exist is an empty group.
    try:
        info = _snapd_quotas.get_quota(group)
    except _errors.QuotaNotFoundError:
        info = None
    current_snaps = [] if info is None else info.snaps
    current_services: dict[str, list[str]] = {} if info is None else info.services
    current_parent = None if info is None else info.parent
    current_constraints: dict[str, Any] = {} if info is None else dict(info._constraints)
    # 3. Build the target from a copy of the current group, applying what was given.
    # Entries snapd reports that this function has no argument for (such as journal)
    # are copied through untouched.
    target_snaps = current_snaps if snaps_list is None else snaps_list
    target_services = current_services if services_dict is None else services_dict
    target_parent = current_parent if parent is _utils.UNCHANGED else parent
    target_constraints = dict(current_constraints)
    for key, value in given.items():
        if value is None:
            target_constraints.pop(key, None)
        else:
            target_constraints[key] = value
    # 4. A group that doesn't exist is created as the target.
    if info is None:
        _create_quota(group, target_snaps, target_services, target_parent, target_constraints)
        return True
    # 5. A group that already matches is left alone.
    if (
        _same_names(current_snaps, target_snaps)
        and _same_services(current_services, target_services)
        and current_parent == target_parent
        and _same_constraints(current_constraints, target_constraints)
    ):
        return False
    # 6-7. A target reachable by adding to the current group is reached with one 'ensure'
    # request carrying only what the group lacks.
    if _can_update_quota_in_place(
        current_snaps,
        current_services,
        current_parent,
        current_constraints,
        target_snaps,
        target_services,
        target_parent,
        target_constraints,
    ):
        new_snaps = [s for s in target_snaps if s not in set(current_snaps)]
        new_services = {
            snap: [name for name in names if name not in set(current_services.get(snap, []))]
            for snap, names in target_services.items()
        }
        changed = {
            key: value
            for key, value in target_constraints.items()
            if not _same_constraint_entry(key, current_constraints.get(key), value)
        }
        named = [*new_snaps, *new_services]
        try:
            _snapd_quotas._post_ensure(
                group,
                snaps=new_snaps,
                services=_snapd_quotas._qualified_services(new_services),
                constraints=changed,
            )
        except _errors.APIError:
            _snapd_quotas._raise_if_not_installed(named)
            raise
        return True
    # 8. Anything else re-creates the group.
    # Check the named snaps first, so that a wrong snap name cannot delete a working group.
    _snapd_quotas._raise_if_not_installed([*target_snaps, *target_services])
    # A group with sub-groups cannot be removed: QuotaHasSubgroupsError escapes here,
    # before anything has changed.
    _snapd_quotas.remove_quota(group)
    _create_quota(group, target_snaps, target_services, target_parent, target_constraints)
    return True


def _create_quota(
    group: str,
    snaps: Iterable[str],
    services: Mapping[str, Iterable[str]],
    parent: str | None,
    constraints: Mapping[str, Any],
) -> None:
    """Create a quota group with the full target description, in a single 'ensure' request."""
    try:
        _snapd_quotas._post_ensure(
            group,
            snaps=snaps,
            services=_snapd_quotas._qualified_services(services),
            parent=parent,
            constraints=constraints,
        )
    except _errors.APIError:
        _snapd_quotas._raise_if_not_installed([*snaps, *services])
        raise


def _same_names(current: Iterable[str], target: Iterable[str]) -> bool:
    """Compare two collections of names, ignoring order."""
    return set(current) == set(target)


def _same_services(
    current: Mapping[str, Iterable[str]], target: Mapping[str, Iterable[str]]
) -> bool:
    """Compare two snap-to-services mappings, ignoring order within each snap."""
    return set(current) == set(target) and all(
        set(current[snap]) == set(target[snap]) for snap in current
    )


def _same_constraints(current: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    """Compare two raw constraint dicts as snapd reports them."""
    return set(current) == set(target) and all(
        _same_constraint_entry(key, current[key], target[key]) for key in current
    )


def _same_constraint_entry(key: str, current: Any, target: Any) -> bool:
    """Compare a single constraint entry, comparing a CPU set's cores ignoring order."""
    if key == 'cpu-set' and isinstance(current, dict) and isinstance(target, dict):
        current_cpus: Any = typing.cast('dict[str, Any]', current).get('cpus') or []
        target_cpus: Any = typing.cast('dict[str, Any]', target).get('cpus') or []
        return set(current_cpus) == set(target_cpus)
    return current == target


def _can_update_quota_in_place(
    current_snaps: Iterable[str],
    current_services: Mapping[str, Iterable[str]],
    current_parent: str | None,
    current_constraints: Mapping[str, Any],
    target_snaps: Iterable[str],
    target_services: Mapping[str, Iterable[str]],
    target_parent: str | None,
    target_constraints: Mapping[str, Any],
) -> bool:
    """Whether the target can be reached by adding to the current group.

    Mirrors the limits of snapd's 'ensure' action: the parent must be the same, every
    snap and service must still be there, no constraint entry may be deleted, and the
    memory and threads limits may be raised but not lowered. The CPU limit may change up
    or down in place.
    """
    if current_parent != target_parent:
        return False
    if not set(current_snaps) <= set(target_snaps):
        return False
    for snap_name, names in current_services.items():
        if not set(names) <= set(target_services.get(snap_name, [])):
            return False
    for key in current_constraints:
        if key not in target_constraints:
            return False
    for key in ('memory', 'threads'):
        current_value = current_constraints.get(key)
        target_value = target_constraints.get(key)
        if current_value is not None and target_value is not None and target_value < current_value:
            return False
    return True
