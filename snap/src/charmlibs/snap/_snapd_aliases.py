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

"""Snap alias operations, implemented as calls to the snapd REST API's /v2/aliases endpoint."""

from __future__ import annotations

import logging

from . import _client, _utils

logger = logging.getLogger(__name__)


def alias(snap: str, app: str, alias: str) -> None:
    """Create an alias for a snap app.

    If the alias already exists for the same snap, this call succeeds silently,
    reassigning the alias to the new app if it differs.

    Args:
        snap: The name of the snap that owns the app.
        app: The name of the app within the snap to alias.
        alias: The alias (command name) to create for the app.

    Raises:
        ValueError: if the snap name, app name, or alias is empty or blank.
        NotInstalledError: if the snap is not installed.
        ChangeError: if the alias name is already claimed by a different snap,
            conflicts with the command namespace of an installed snap,
            or if the specified app does not exist within the snap.
    """
    for value, label in ((snap, 'snap name'), (app, 'app name'), (alias, 'alias')):
        if problem := _utils.check_empty_or_blank(value):
            raise ValueError(f'{label} {problem}')
    data = {'action': 'alias', 'snap': snap, 'app': app, 'alias': alias}
    _client.post('/v2/aliases', body=data)


def unalias(alias: str) -> None:
    """Remove an alias.

    Args:
        alias: The alias to remove.

    Raises:
        ValueError: if the alias is empty or blank.
        ChangeError: if the alias removal fails after starting.
        APIError: if the alias does not exist (for example, was never created, or the snap it
            belonged to was removed — aliases do not survive snap removal).
    """
    if problem := _utils.check_empty_or_blank(alias):
        raise ValueError(f'alias {problem}')
    data = {'action': 'unalias', 'alias': alias}
    _client.post('/v2/aliases', body=data)
