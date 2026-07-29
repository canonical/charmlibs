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

"""Snap app/service operations, implemented as calls to the snapd REST API's /v2/apps endpoint."""

from __future__ import annotations

import typing
from typing import Any

from . import _client, _errors, _utils

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

# /v2/apps


def start(snap: str, services: str | Iterable[str] | None = None, *, enable: bool = False) -> None:
    """Start snap services.

    Args:
        snap: The name of the snap whose services to start.
        services: Names of services within the snap to start, as a single name or an iterable of
            names. If ``None`` (the default), all of the snap's services are started. If an empty
            iterable, no services are started and no request is made -- but the snap must still
            be installed.
        enable: If ``True``, also enable the services to start automatically at boot.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if a
            service name is empty or blank.
        NotFoundError: if the snap is not installed.
        AppNotFoundError: if the snap is installed but has no service with a given name, or if
            all services were requested and the snap has no services at all.
        ChangeError: if the change fails (for example, the service fails to start).

    ::

        # Start every service the snap has.
        start('lxd')
        # Start one service.
        start('lxd', 'daemon')
        # Start several.
        start('lxd', ['daemon', 'user-daemon'])
        # Start none of them -- a no-op, but still an error if lxd isn't installed.
        start('lxd', [])
    """
    _post_action('start', snap, services, {'enable': True} if enable else None)


def stop(snap: str, services: str | Iterable[str] | None = None, *, disable: bool = False) -> None:
    """Stop snap services.

    Args:
        snap: The name of the snap whose services to stop.
        services: Names of services within the snap to stop, as a single name or an iterable of
            names. If ``None`` (the default), all of the snap's services are stopped. If an empty
            iterable, no services are stopped and no request is made -- but the snap must still
            be installed.
        disable: If ``True``, also disable the services from starting automatically at boot.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if a
            service name is empty or blank.
        NotFoundError: if the snap is not installed.
        AppNotFoundError: if the snap is installed but has no service with a given name, or if
            all services were requested and the snap has no services at all.
        ChangeError: if the change fails (for example, the service fails to stop).
    """
    _post_action('stop', snap, services, {'disable': True} if disable else None)


def restart(snap: str, services: str | Iterable[str] | None = None) -> None:
    """Restart snap services.

    Args:
        snap: The name of the snap whose services to restart.
        services: Names of services within the snap to restart, as a single name or an iterable
            of names. If ``None`` (the default), all of the snap's services are restarted. If an
            empty iterable, no services are restarted and no request is made -- but the snap must
            still be installed.

    Raises:
        ValueError: if the snap name is empty, blank, or is not a single path segment, or if a
            service name is empty or blank.
        NotFoundError: if the snap is not installed.
        AppNotFoundError: if the snap is installed but has no service with a given name, or if
            all services were requested and the snap has no services at all.
        ChangeError: if the change fails (for example, the service fails to restart).
    """
    _post_action('restart', snap, services)


def _post_action(
    action: str,
    snap: str,
    services: str | Iterable[str] | None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Validate the arguments and post an action for a snap's services to /v2/apps.

    Makes no request when no services were requested, beyond confirming the snap is installed.
    """
    # NOTE: The name is sent in the request body rather than the path, but it's validated as a
    # path segment all the same -- a name that isn't one can't be a snap, and the not-installed
    # probe below builds a path from it, where an unusable name would raise ValueError from
    # inside an exception handler and mask the error being classified.
    _utils.raise_if_not_path_segment(snap)
    services = None if services is None else _utils.as_list(services)
    if services is not None:
        _utils.raise_if_empty_or_blank(services, label='service name')
        if not services:
            # NOTE: No services were requested, so there is nothing to act on. The snap itself is
            # still named, so it's checked the way a request naming a service would have checked
            # it: asking a snap that isn't installed to do nothing is an error, not a no-op.
            # 'system'/'core' get no special treatment here -- /v2/apps has no system alias, and
            # core is an ordinary snap to it.
            if error := _utils.check_installed(snap):
                raise error
            return
    # NOTE: Naming the snap itself is how snapd is asked to act on all of its services.
    names = [f'{snap}.{service}' for service in services] if services else [snap]
    body: dict[str, Any] = {'action': action, 'names': names, **(extra or {})}
    try:
        _client.post('/v2/apps', body=body)
    except _errors.AppNotFoundError:
        # NOTE: snapd answers app-not-found both for a snap that isn't installed and for a service
        # that an installed snap doesn't have. We probe /v2/snaps/{snap} so that an absent snap
        # raises NotFoundError, as it does elsewhere in the library, which leaves AppNotFoundError
        # meaning what it says: the snap is installed, but has no such service.
        if error := _utils.check_installed(snap):
            raise error from None
        raise
