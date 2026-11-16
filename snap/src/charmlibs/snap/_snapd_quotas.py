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

"""Snap quota group operations, implemented as calls to the snapd API's /v2/quotas endpoint."""

from __future__ import annotations

import typing
from typing import Any

from . import _client, _errors, _utils

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from typing_extensions import Self

# /v2/quotas


class QuotaInfo:
    """Information about a quota group."""

    def __init__(
        self,
        name: str,
        parent: str | None,
        subgroups: Iterable[str],
        snaps: Iterable[str],
        services: Mapping[str, Iterable[str]],
        memory: int | None,
        cpu: tuple[int | None, int] | None,
        cpu_set: Iterable[int] | None,
        threads: int | None,
        memory_usage: int | None,
        threads_usage: int | None,
        constraints: Mapping[str, Any],
    ):
        self._name = name
        self._parent = parent
        self._subgroups = list(subgroups)
        self._snaps = list(snaps)
        self._services = {snap: list(names) for snap, names in services.items()}
        self._memory = memory
        self._cpu = cpu
        self._cpu_set = None if cpu_set is None else list(cpu_set)
        self._threads = threads
        self._memory_usage = memory_usage
        self._threads_usage = threads_usage
        # The constraints as snapd reported them (minus its empty cpu/cpu-set entries, see
        # _from_dict), so that ensure_quota can carry over limits it was not asked about --
        # including kinds this library has no argument for, such as journal quotas.
        self._constraints = dict(constraints)

    @classmethod
    def _from_dict(cls, info_dict: dict[str, Any]) -> Self:
        constraints: dict[str, Any] = dict(info_dict.get('constraints') or {})
        current: dict[str, Any] = info_dict.get('current') or {}
        # NOTE: snapd omits zero values and empty lists from its response, so a missing or
        # zero limit means "not set", and is reported here as None. The exception is that it
        # reports cpu and cpu-set together whenever either is set, with the unused one an
        # empty object -- and an empty entry means "not set" too. Drop those two from the
        # raw constraints, so that comparing groups (or carrying constraints over a
        # re-create) never reads them as set. An empty journal entry, by contrast, is
        # meaningful -- a journal quota with no size or rate -- and is kept.
        cpu_dict: dict[str, Any] = constraints.get('cpu') or {}
        if not cpu_dict.get('percentage'):
            constraints.pop('cpu', None)
        cpu_set_dict: dict[str, Any] = constraints.get('cpu-set') or {}
        if not cpu_set_dict.get('cpus'):
            constraints.pop('cpu-set', None)
        memory = constraints.get('memory') or None
        threads = constraints.get('threads') or None
        percentage = cpu_dict.get('percentage') or None
        # A count of zero (or absent) means the percentage applies to every available core.
        cpu = (cpu_dict.get('count') or None, percentage) if percentage is not None else None
        cpu_set = cpu_set_dict.get('cpus') or None
        raw_services: list[str] = info_dict.get('services') or []
        services: dict[str, list[str]] = {}
        for qualified in raw_services:
            snap_name, _, service = qualified.partition('.')
            services.setdefault(snap_name, []).append(service)
        return cls(
            name=info_dict['group-name'],
            parent=info_dict.get('parent') or None,
            subgroups=info_dict.get('subgroups') or [],
            snaps=info_dict.get('snaps') or [],
            services=services,
            memory=memory,
            cpu=cpu,
            cpu_set=cpu_set,
            threads=threads,
            # Usage is only reported for a limit that is set, and is reported as 0 when the
            # group's snaps are idle, rather than being absent from the response.
            memory_usage=(current.get('memory') or 0) if memory is not None else None,
            threads_usage=(current.get('threads') or 0) if threads is not None else None,
            constraints=constraints,
        )

    @property
    def name(self) -> str:
        """The quota group's name."""
        return self._name

    @property
    def parent(self) -> str | None:
        """The name of the group's parent group, or None if it is a top-level group."""
        return self._parent

    @property
    def subgroups(self) -> list[str]:
        """The names of the group's direct sub-groups."""
        return self._subgroups

    @property
    def snaps(self) -> list[str]:
        """The names of the snaps in the group."""
        return self._snaps

    @property
    def services(self) -> dict[str, list[str]]:
        """The services in the group, as a mapping of snap name to service names.

        snapd reports services as qualified ``snap.service`` names; they are split here at
        the first dot, matching the form :func:`set_quota` accepts.
        """
        return self._services

    @property
    def memory(self) -> int | None:
        """The memory limit in bytes, or None if no memory limit is set."""
        return self._memory

    @property
    def cpu(self) -> tuple[int | None, int] | None:
        """The CPU limit as a ``(count, percentage)`` pair, or None if no CPU limit is set.

        ``(2, 50)`` is the CLI's ``2x50%``. A count of None means the percentage applies to
        every available core: ``(None, 50)`` is the CLI's ``50%``.
        """
        return self._cpu

    @property
    def cpu_set(self) -> list[int] | None:
        """The indices of the cores the group may use, or None if no CPU set limit is set."""
        return self._cpu_set

    @property
    def threads(self) -> int | None:
        """The threads limit, or None if no threads limit is set."""
        return self._threads

    @property
    def memory_usage(self) -> int | None:
        """The group's current memory usage in bytes, or None if no memory limit is set.

        Usage is only measured against a limit, so this is None when :attr:`memory` is None,
        and 0 when the group's snaps are idle.
        """
        return self._memory_usage

    @property
    def threads_usage(self) -> int | None:
        """The group's current thread count, or None if no threads limit is set.

        Usage is only measured against a limit, so this is None when :attr:`threads` is None.
        """
        return self._threads_usage

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}('
            f'{self.name!r}'
            f', parent={self.parent!r}'
            f', subgroups={self.subgroups!r}'
            f', snaps={self.snaps!r}'
            f', services={self.services!r}'
            f', memory={self.memory!r}'
            f', cpu={self.cpu!r}'
            f', cpu_set={self.cpu_set!r}'
            f', threads={self.threads!r}'
            f', memory_usage={self.memory_usage!r}'
            f', threads_usage={self.threads_usage!r}'
            ')'
        )


def get_quota(group: str) -> QuotaInfo:
    """Get information about a single quota group.

    Args:
        group: The name of the quota group.

    Returns:
        A :class:`QuotaInfo` object with the group's snaps, services, and limits.

    Raises:
        ValueError: if the group name is empty, blank, or is not a single path segment.
        QuotaNotFoundError: if the quota group does not exist.
        BadResponseError: if snapd's description of the group isn't one we can read.
    """
    path = f'/v2/quotas/{_utils.snap_path_segment(group, label="group name")}'
    try:
        result = _client.get(path)
    except _errors.APIError as e:
        # This endpoint answers 404 only when the group does not exist.
        if e._status_code == 404:
            raise _errors.QuotaNotFoundError._from(e) from None
        raise
    if not isinstance(result, dict):
        raise _errors.BadResponseError(
            message=f'Unexpected response type {type(result).__name__!r} for quota group {group!r}, expected a "dict"',  # noqa: E501
            response=result,
        )
    result = typing.cast('dict[str, Any]', result)
    try:
        return QuotaInfo._from_dict(result)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise _errors.BadResponseError(
            message=f"Could not read snapd's description of quota group {group!r}: {e!r}",
            response=result,
        ) from None


def list_quotas() -> list[QuotaInfo]:
    """List every quota group.

    Returns:
        A list of :class:`QuotaInfo` objects, sorted by group name. Empty if there are none.

    Raises:
        BadResponseError: if snapd's description of the groups isn't one we can read.
    """
    result = _client.get('/v2/quotas')
    if not isinstance(result, list):
        raise _errors.BadResponseError(
            message=f'Unexpected response type {type(result).__name__!r} for /v2/quotas, expected a "list"',  # noqa: E501
            response=result,
        )
    infos: list[QuotaInfo] = []
    entries = typing.cast('list[Any]', result)
    for entry in entries:
        if not isinstance(entry, dict):
            raise _errors.BadResponseError(
                message=f'Unexpected entry type {type(entry).__name__!r} in /v2/quotas response, expected a "dict"',  # noqa: E501
                response=entries,
            )
        try:
            infos.append(QuotaInfo._from_dict(typing.cast('dict[str, Any]', entry)))
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise _errors.BadResponseError(
                message=f"Could not read snapd's description of a quota group: {e!r}",
                response=entries,
            ) from None
    return infos


def set_quota(
    group: str,
    snaps: str | Iterable[str] | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    *,
    services: Mapping[str, str | Iterable[str]] | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    parent: str | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    memory: int | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    cpu: tuple[int | None, int] | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    cpu_set: Iterable[int] | type[_utils.UNCHANGED] = _utils.UNCHANGED,
    threads: int | type[_utils.UNCHANGED] = _utils.UNCHANGED,
) -> None:
    """Create a quota group, or add to an existing one.

    This is a thin mirror of ``snap set-quota``: it sends a single request and waits for
    the change. Like the CLI, it is **additive** and **not idempotent**:

    - It can add snaps and services, add a limit that was not set, raise the memory or
      threads limit, and change the CPU limit up or down. It cannot remove a snap or
      service, remove a limit, lower the memory or threads limit, or change the parent --
      those need the group to be removed and created again, which :func:`ensure_quota`
      does.
    - Naming a snap or service that is already in a group -- even the group being updated --
      is an error in snapd. Call :func:`get_quota` first, or use :func:`ensure_quota`,
      which never re-sends what a group already has.

    Every argument except ``group`` defaults to :data:`UNCHANGED`, meaning it is left out
    of the request entirely. An empty ``snaps`` or ``services`` is accepted and adds
    nothing, the same as ``UNCHANGED``. ``None`` is not accepted: since this function can
    only add, "must be absent" has no meaning for it -- use :func:`ensure_quota` to remove
    a limit or parent.

    Note that snapd requires a new group to have at least one limit.

    Args:
        group: The name of the quota group.
        snaps: Snaps to add to the group, as a single name or an iterable of names.
        services: Services to add to the group, as a mapping of snap name to service
            names: ``{'some-snap': ['serv1', 'serv2']}``.
        parent: The name of an existing group to nest this group under. Ignored by snapd
            if the group already exists.
        memory: The memory limit in bytes. The library does no unit parsing.
        cpu: The CPU limit as a ``(count, percentage)`` pair: ``(2, 50)`` is the CLI's
            ``2x50%``. A count of None means the percentage applies to every available
            core: ``(None, 50)`` is the CLI's ``50%``. Percentage is 1 to 100.
        cpu_set: The indices of the cores the group may use.
        threads: The threads limit.

    Raises:
        ValueError: if the group name is empty, blank, or is not a single path segment; if
            a snap name (in ``snaps`` or ``services``) is empty, blank, or is not a single
            path segment; if a service name is empty or blank; if ``parent`` is a string
            that is empty, blank, or is not a single path segment; if ``memory`` or
            ``threads`` is zero or negative; if the CPU percentage is outside 1 to 100 or
            the CPU count is zero or negative; or if ``cpu_set`` is empty or contains a
            negative number.
        TypeError: if ``parent`` or a limit is None.
        NotInstalledError: if a snap named in ``snaps`` or ``services`` is not installed.
        APIError: for the rules left to snapd -- for example, a group name with invalid
            characters, snaps and services mixed in one group, a limit lowered, a named
            snap already in a group, or a parent that does not exist.
        ChangeError: if the operation fails after starting.

    ::

        # Create a group limiting my-snap to 512 MiB of memory.
        set_quota('my-group', 'my-snap', memory=512 * 1024**2)
        # Add another snap to it, and limit it to half of every CPU core.
        set_quota('my-group', 'my-other-snap', cpu=(None, 50))
    """
    _utils.raise_if_not_path_segment(group, label='group name')
    snaps_list = None if snaps is _utils.UNCHANGED else _validate_snaps(snaps)
    services_dict = None if services is _utils.UNCHANGED else _validate_services(services)
    _reject_none(parent, 'parent')
    if parent is not _utils.UNCHANGED:
        # snapd stores no parent when it gets an empty one, so reading the group back
        # would never show what was sent. Reject it rather than send it nowhere.
        _utils.raise_if_not_path_segment(parent, label='parent group name')
    _reject_none(memory, 'memory')
    _reject_none(cpu, 'cpu')
    _reject_none(cpu_set, 'cpu_set')
    _reject_none(threads, 'threads')
    constraints: dict[str, Any] = {}
    if memory is not _utils.UNCHANGED:
        _validate_memory(memory)
        constraints['memory'] = memory
    if cpu is not _utils.UNCHANGED:
        constraints['cpu'] = _validate_cpu(cpu)
    if cpu_set is not _utils.UNCHANGED:
        constraints['cpu-set'] = {'cpus': _validate_cpu_set(cpu_set)}
    if threads is not _utils.UNCHANGED:
        _validate_threads(threads)
        constraints['threads'] = threads
    named = [*(snaps_list or []), *(services_dict or {})]
    try:
        _post_ensure(
            group,
            snaps=snaps_list or (),
            services=_qualified_services(services_dict) if services_dict is not None else (),
            parent=None if parent is _utils.UNCHANGED else parent,
            constraints=constraints,
        )
    except _errors.APIError:
        # Turn snapd's kindless 'cannot use snap ...' error into a typed NotInstalledError.
        _raise_if_not_installed(named)
        raise


def remove_quota(group: str) -> None:
    """Remove a quota group.

    Sends a single request and waits for the change. The snaps in the group are not
    affected, beyond losing the group's limits. Sub-groups are not removed: a group that
    has sub-groups cannot be removed until they are.

    Args:
        group: The name of the quota group.

    Raises:
        ValueError: if the group name is empty, blank, or is not a single path segment.
        QuotaNotFoundError: if the quota group does not exist.
        QuotaHasSubgroupsError: if the group has sub-groups. Nothing is changed in this
            case; remove the sub-groups first.
        ChangeError: if the operation fails after starting.
    """
    _utils.raise_if_not_path_segment(group, label='group name')
    try:
        _client.post('/v2/quotas', body={'action': 'remove', 'group-name': group})
    except _errors.APIError as e:
        # NOTE: snapd's failure message alone doesn't say whether the group was missing or
        # had sub-groups, so classify from a fresh lookup rather than the message.
        try:
            info = get_quota(group)
        except _errors.QuotaNotFoundError:
            raise _errors.QuotaNotFoundError._from(e) from None
        if info.subgroups:
            raise _errors.QuotaHasSubgroupsError._from(e) from None
        raise


########################################################
# Building and validating the arguments of an 'ensure' #
########################################################


def _post_ensure(
    group: str,
    *,
    snaps: Iterable[str] = (),
    services: Iterable[str] = (),
    parent: str | None = None,
    constraints: Mapping[str, Any] | None = None,
) -> None:
    """POST a single 'ensure' action for a quota group, waiting for the change.

    Takes the constraints as a raw dict in snapd's shape, so that callers carrying over
    limits read back from snapd can send them unchanged. Whatever was not given -- empty
    snaps or services, no parent, no constraints -- is left out of the request body.
    """
    body: dict[str, Any] = {'action': 'ensure', 'group-name': group}
    if parent is not None:
        body['parent'] = parent
    snaps = list(snaps)
    if snaps:
        body['snaps'] = snaps
    services = list(services)
    if services:
        body['services'] = services
    if constraints:
        body['constraints'] = dict(constraints)
    _client.post('/v2/quotas', body=body)


def _validate_snaps(snaps: str | Iterable[str]) -> list[str]:
    """Normalise a one-or-many snap argument to a list, rejecting unusable names.

    Names are validated as path segments, not just as empty or blank, because the
    not-installed probe on a failed request builds a path from each name: a name that
    can't be a path segment would raise ValueError from inside the exception handler and
    mask the error snapd sent (the same trap _snapd_apps._post_action documents).
    """
    names = _utils.as_list(snaps)
    for name in names:
        _utils.raise_if_not_path_segment(name)
    return names


def _validate_services(services: Mapping[str, str | Iterable[str]]) -> dict[str, list[str]]:
    """Normalise a services mapping's values to lists, rejecting unusable names.

    Snap names (the keys) are validated as path segments like any other snap name (see
    :func:`_validate_snaps`); service names get the empty-or-blank check only.

    A snap mapped to an empty list contributes no services, so the entry is dropped:
    ``{'some-snap': []}`` means the same as not mentioning ``some-snap`` at all.
    """
    result: dict[str, list[str]] = {}
    for snap_name, names in services.items():
        _utils.raise_if_not_path_segment(snap_name)
        names_list = _utils.as_list(names)
        _utils.raise_if_empty_or_blank(names_list, label='service name')
        if names_list:
            result[snap_name] = names_list
    return result


def _qualified_services(services: Mapping[str, Iterable[str]]) -> list[str]:
    """Flatten a services mapping to the qualified ``snap.service`` names snapd expects."""
    return [f'{snap}.{name}' for snap, names in services.items() for name in names]


def _reject_none(value: object, name: str) -> None:
    """Raise TypeError if a value is None.

    set_quota can only add to a group, so "must be absent" -- what None means for
    ensure_quota -- has no meaning for it. The TypeError points the caller to the
    function that can remove things.
    """
    if value is None:
        raise TypeError(
            f'{name} cannot be None: set_quota can only add to a quota group, '
            f'use ensure_quota to remove a limit or parent'
        )


def _validate_memory(memory: int) -> None:
    """Raise ValueError for a memory limit snapd would drop or mishandle silently."""
    if memory <= 0:
        raise ValueError(f'memory must be a positive number of bytes, not {memory!r}')


def _validate_cpu(cpu: tuple[int | None, int]) -> dict[str, int]:
    """Raise ValueError for a CPU pair snapd would mishandle, and return it in snapd's shape.

    The count is left out when it is None, so that the percentage applies to every
    available core: sending a percentage with no count resets the count to all cores.
    """
    count, percentage = cpu
    if not 1 <= percentage <= 100:
        raise ValueError(f'cpu percentage must be between 1 and 100, not {percentage!r}')
    if count is not None and count <= 0:
        raise ValueError(f'cpu count must be a positive integer, not {count!r}')
    return {'percentage': percentage, **({} if count is None else {'count': count})}


def _validate_cpu_set(cpu_set: Iterable[int]) -> list[int]:
    """Raise ValueError for a CPU set snapd would drop or mishandle silently."""
    cpus = list(cpu_set)
    if not cpus:
        raise ValueError('cpu_set must not be empty')
    if any(cpu < 0 for cpu in cpus):
        raise ValueError(f'cpu_set must not contain negative core indices: {cpus!r}')
    return cpus


def _validate_threads(threads: int) -> None:
    """Raise ValueError for a threads limit snapd would drop or mishandle silently."""
    if threads <= 0:
        raise ValueError(f'threads must be a positive integer, not {threads!r}')


def _raise_if_not_installed(snaps: Iterable[str]) -> None:
    """Raise NotInstalledError for the first named snap that is absent, if any."""
    for name in snaps:
        if error := _utils.check_installed(name):
            raise error from None
