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

"""Utils for integration tests."""

import json
from datetime import datetime

import jubilant

TRACE_FILE = '/var/lib/charm-rolling-ops/transitions.log'


def get_unit_events(juju: jubilant.Juju, unit: str) -> list[dict[str, str]]:
    task = juju.exec(f'cat {TRACE_FILE}', unit=unit)

    if not task.stdout.strip():
        return []

    return [json.loads(line) for line in task.stdout.strip().splitlines()]


def parse_ts(event: dict[str, str]) -> datetime:
    return datetime.fromisoformat(event['ts'])


def get_leader_unit_name(juju: jubilant.Juju, app: str) -> str:
    """Retrieve the leader unit's name.

    Raises:
        RuntimeError: if no leader unit is found.
    """
    for name, unit in juju.status().get_units(app).items():
        if unit.leader:
            return name

    raise RuntimeError(f'No leader unit found for app {app}')


def remove_transition_file(juju: jubilant.Juju, unit: str):
    juju.exec(f'rm -f {TRACE_FILE}', unit=unit)


def is_empty_file(juju: jubilant.Juju, unit: str, path: str) -> bool:
    task = juju.exec(f'test ! -s {path}', unit=unit)
    if task.status != 'completed' or task.return_code != 0:
        return False
    return True
