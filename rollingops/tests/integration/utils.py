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

import datetime as dt
import json
import time

import jubilant

from charmlibs import pathops

TRACE_FILE = '/var/lib/charm-rolling-ops/transitions.log'
POLL_INTERVAL = 5.0


def get_unit_events(juju: jubilant.Juju, unit: str) -> list[dict[str, str]]:
    task = juju.exec(f'cat {TRACE_FILE}', unit=unit)

    if not task.stdout.strip():
        return []

    return [json.loads(line) for line in task.stdout.strip().splitlines()]


def wait_for_events(
    juju: jubilant.Juju,
    unit: str,
    count: int,
    timeout: float,
    ignore_actions: bool = True,
) -> list[dict[str, str]]:
    """Poll a unit's trace file until it has recorded at least ``count`` events.

    Rolling operations are executed by a background worker that polls etcd, so
    the delay between requesting an operation and executing it is not bounded by
    the request itself. Tests must wait for the events they expect rather than
    for a fixed amount of time.

    Args:
        juju: The Juju client to run commands with.
        unit: Name of the unit whose trace file should be polled.
        count: Minimum number of matching events to wait for.
        timeout: Maximum time in seconds to wait.
        ignore_actions: Whether ``action:*`` events are excluded from the count.

    Returns:
        The events recorded by the unit, including ``action:*`` events.

    Raises:
        TimeoutError: If the unit did not record ``count`` events in time.
    """
    deadline = time.monotonic() + timeout
    events: list[dict[str, str]] = []
    while True:
        events = get_unit_events(juju, unit)
        matching = [e for e in events if not (ignore_actions and e['event'].startswith('action'))]
        if len(matching) >= count:
            return events
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f'{unit} recorded {len(matching)} of {count} expected events '
                f'in {timeout}s: {matching}'
            )
        time.sleep(POLL_INTERVAL)


def wait_for_event(juju: jubilant.Juju, unit: str, event: str, timeout: float) -> None:
    """Poll a unit's trace file until it has recorded the named event.

    Args:
        juju: The Juju client to run commands with.
        unit: Name of the unit whose trace file should be polled.
        event: Name of the event to wait for, e.g. ``_restart:start``.
        timeout: Maximum time in seconds to wait.

    Raises:
        TimeoutError: If the unit did not record the event in time.
    """
    deadline = time.monotonic() + timeout
    while True:
        events = get_unit_events(juju, unit)
        if any(e['event'] == event for e in events):
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f'{unit} did not record {event} within {timeout}s: {events}')
        time.sleep(POLL_INTERVAL)


def parse_ts(event: dict[str, str]) -> dt.datetime:
    return dt.datetime.fromtimestamp(float(event['ts']), tz=dt.timezone.utc)


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
    pathops_path = pathops.LocalPath(path)
    try:
        task = juju.exec(f'test ! -s {pathops_path}', unit=unit)
    except Exception:
        return False

    return task.status == 'completed' and task.return_code == 0
