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

from typing import Any

from . import _client

# /v2/apps


def start(snap: str, *services: str, enable: bool = False) -> None:
    """Start snap services.

    Args:
        snap: The name of the snap whose services to start.
        services: Names of services within the snap to start. If omitted, all of the snap's
            services are started.
        enable: If ``True``, also enable the services to start automatically at boot.

    Raises:
        AppNotFoundError: if the snap is not installed or the service is not found.
        ChangeError: if the change fails (for example, the service fails to start).
    """
    names = [f'{snap}.{s}' for s in services] if services else [snap]
    data: dict[str, Any] = {'action': 'start', 'names': names}
    if enable:
        data['enable'] = True
    _client.post('/v2/apps', body=data)


def stop(snap: str, *services: str, disable: bool = False) -> None:
    """Stop snap services.

    Args:
        snap: The name of the snap whose services to stop.
        services: Names of services within the snap to stop. If omitted, all of the snap's
            services are stopped.
        disable: If ``True``, also disable the services from starting automatically at boot.

    Raises:
        AppNotFoundError: if the snap is not installed or the service is not found.
        ChangeError: if the change fails (for example, the service fails to stop).
    """
    names = [f'{snap}.{s}' for s in services] if services else [snap]
    data: dict[str, Any] = {'action': 'stop', 'names': names}
    if disable:
        data['disable'] = True
    _client.post('/v2/apps', body=data)


def restart(snap: str, *services: str) -> None:
    """Restart snap services.

    Args:
        snap: The name of the snap whose services to restart.
        services: Names of services within the snap to restart. If omitted, all of the snap's
            services are restarted.

    Raises:
        AppNotFoundError: if the snap is not installed or the service is not found.
        ChangeError: if the change fails (for example, the service fails to restart).
    """
    names = [f'{snap}.{s}' for s in services] if services else [snap]
    data: dict[str, Any] = {'action': 'restart', 'names': names}
    _client.post('/v2/apps', body=data)
