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

"""Integration tests using real Juju and pre-packed charm(s)."""

import logging
import time

import jubilant

from tests.integration.utils import (
    get_leader_unit_name,
    get_unit_events,
    parse_ts,
    remove_transition_file,
)

logger = logging.getLogger(__name__)
TIMEOUT = 15 * 60.0


def test_deploy(juju: jubilant.Juju, app_name: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert app_name in juju.status().apps


def test_restart_action_one_unit(juju: jubilant.Juju, app_name: str):
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)
    unit = f'{app_name}/0'

    juju.run(unit, 'restart', {'delay': 1}, wait=TIMEOUT)

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    events = get_unit_events(juju, unit)
    restart_events = [e['event'] for e in events]

    expected = [
        'action:restart',
        '_restart:start',
        '_restart:done',
    ]

    assert restart_events == expected, f'unexpected event order: {restart_events}'


def test_failed_restart_retries_one_unit(juju: jubilant.Juju, app_name: str):
    unit = f'{app_name}/0'

    remove_transition_file(juju, unit)
    juju.run(unit, 'failed-restart', {'delay': 1, 'max-retry': 2})
    juju.run(unit, 'restart', {'delay': 1})

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    events = get_unit_events(juju, unit)
    restart_events = [e['event'] for e in events]

    expected = [
        'action:failed-restart',
        'action:restart',
        '_failed_restart:start',  # attempt 0
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 1
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 2
        '_failed_restart:retry_release',
        '_restart:start',
        '_restart:done',
    ]

    assert restart_events == expected, f'unexpected event order: {restart_events}'


def test_assert_deferred_restart_retries_one_unit(juju: jubilant.Juju, app_name: str):
    unit = f'{app_name}/0'

    remove_transition_file(juju, unit)
    juju.run(unit, 'deferred-restart', {'delay': 1, 'max-retry': 2}, wait=TIMEOUT)
    juju.run(unit, 'restart', {'delay': 1})

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    events = get_unit_events(juju, unit)
    restart_events = [e['event'] for e in events]

    expected = [
        'action:deferred-restart',
        'action:restart',
        '_deferred_restart:start',  # attempt 0
        '_deferred_restart:retry_hold',
        '_deferred_restart:start',  # retry 1
        '_deferred_restart:retry_hold',
        '_deferred_restart:start',  # retry 2
        '_deferred_restart:retry_hold',
        '_restart:start',
        '_restart:done',
    ]

    assert restart_events == expected, f'unexpected event order: {restart_events}'


def test_assert_restart_rolls_one_unit_at_a_time(juju: jubilant.Juju, app_name: str):
    juju.add_unit(app=app_name, num_units=4)
    juju.wait(  # TODO: wait for 5 units to be active
        lambda status: (
            app_name in status.apps
            and len(status.apps[app_name].units) == 5
            and sum(1 for u in status.apps[app_name].units.values() if u.is_active) >= 4
        ),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    status = juju.status()
    units = sorted(status.apps[app_name].units)

    for unit in units:
        remove_transition_file(juju, unit)

    for unit in units:
        juju.run(unit, 'restart', {'delay': 2})

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    all_events: list[dict[str, str]] = []
    for unit in units:
        events = get_unit_events(juju, unit)
        assert len(events) == 3
        all_events.extend(events)

    restart_events = [e for e in all_events if e['event'] in {'_restart:start', '_restart:done'}]
    restart_events.sort(key=parse_ts)

    logger.info(restart_events)

    for i in range(0, len(restart_events), 2):
        start_event = restart_events[i]
        done_event = restart_events[i + 1]

        assert start_event['event'] == '_restart:start'
        assert done_event['event'] == '_restart:done'
        assert start_event['unit'] == done_event['unit'], (
            f'start/done pair mismatch: {start_event} vs {done_event}'
        )


def test_retry_hold_keeps_lock_on_same_unit(juju: jubilant.Juju, app_name: str):
    status = juju.status()
    units = sorted(status.apps[app_name].units)

    for unit in units:
        remove_transition_file(juju, unit)

    unit_a = units[1]
    unit_b = units[3]

    juju.run(unit_a, 'deferred-restart', {'delay': 15, 'max-retry': 2}, wait=TIMEOUT)
    juju.run(unit_b, 'restart', {'delay': 2}, wait=TIMEOUT)

    juju.wait(
        lambda status: status.apps[app_name].units[unit_b].is_active,
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    all_events: list[dict[str, str]] = []
    all_events.extend(get_unit_events(juju, unit_a))
    all_events.extend(get_unit_events(juju, unit_b))
    all_events.sort(key=parse_ts)

    logger.info(all_events)

    relevant_events = [
        e
        for e in all_events
        if e['event']
        in {
            '_deferred_restart:start',
            '_deferred_restart:retry_hold',
            '_restart:start',
            '_restart:done',
        }
    ]

    sequence = [(e['unit'], e['event']) for e in relevant_events]

    logger.info(sequence)

    assert sequence == [
        (unit_a, '_deferred_restart:start'),  # attempt 0
        (unit_a, '_deferred_restart:retry_hold'),
        (unit_a, '_deferred_restart:start'),  # retry 1
        (unit_a, '_deferred_restart:retry_hold'),
        (unit_a, '_deferred_restart:start'),  # retry 2
        (unit_a, '_deferred_restart:retry_hold'),
        (unit_b, '_restart:start'),
        (unit_b, '_restart:done'),
    ], f'unexpected event sequence: {sequence}'


def test_retry_release_alternates_execution(juju: jubilant.Juju, app_name: str):
    status = juju.status()
    units = sorted(status.apps[app_name].units)
    for unit in units:
        remove_transition_file(juju, unit)

    unit_a = units[2]
    unit_b = units[4]

    juju.run(unit_a, 'failed-restart', {'delay': 10, 'max-retry': 2}, wait=TIMEOUT)
    juju.run(unit_b, 'failed-restart', {'delay': 1, 'max-retry': 2}, wait=TIMEOUT)

    time.sleep(60)  # wait for operation execution. TODO: in charm use lock state to clear status.

    all_events: list[dict[str, str]] = []
    all_events.extend(get_unit_events(juju, unit_a))
    all_events.extend(get_unit_events(juju, unit_b))
    all_events.sort(key=parse_ts)

    logger.info(all_events)

    relevant_events = [
        e
        for e in all_events
        if e['event'] in {'_failed_restart:start', '_failed_restart:retry_release'}
    ]

    sequence = [(e['unit'], e['event']) for e in relevant_events]

    logger.info(sequence)

    assert sequence == [
        (unit_a, '_failed_restart:start'),  # attempt 0
        (unit_a, '_failed_restart:retry_release'),
        (unit_b, '_failed_restart:start'),  # attempt 0
        (unit_b, '_failed_restart:retry_release'),
        (unit_a, '_failed_restart:start'),  # retry 1
        (unit_a, '_failed_restart:retry_release'),
        (unit_b, '_failed_restart:start'),  # retry 1
        (unit_b, '_failed_restart:retry_release'),
        (unit_a, '_failed_restart:start'),  # retry 2
        (unit_a, '_failed_restart:retry_release'),
        (unit_b, '_failed_restart:start'),  # retry 2
        (unit_b, '_failed_restart:retry_release'),
    ], f'unexpected event sequence: {sequence}'


def test_subsequent_lock_request_of_different_ops(juju: jubilant.Juju, app_name: str):
    status = juju.status()
    units = sorted(status.apps[app_name].units)
    for unit in units:
        remove_transition_file(juju, unit)

    unit_a = units[3]
    unit_b = units[4]

    juju.run(unit_b, 'deferred-restart', {'delay': 10, 'max-retry': 2})
    juju.run(unit_a, 'failed-restart', {'delay': 1, 'max-retry': 2})
    juju.run(unit_a, 'deferred-restart', {'delay': 1, 'max-retry': 0})
    juju.run(unit_a, 'restart', {'delay': 1})

    juju.wait(
        lambda status: status.apps[app_name].units[unit_a].is_active,
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    unit_a_events = get_unit_events(juju, unit_a)
    relevant_events = [e['event'] for e in unit_a_events]

    logger.info('unit_a_events %s', unit_a_events)

    assert relevant_events == [
        'action:failed-restart',
        'action:deferred-restart',
        'action:restart',
        '_failed_restart:start',  # attempt 0
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 1
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 2
        '_failed_restart:retry_release',
        '_deferred_restart:start',  # attempt 0
        '_deferred_restart:retry_hold',
        '_restart:start',
        '_restart:done',
    ], f'unexpected event sequence: {relevant_events}'


def test_subsequent_lock_request_of_same_op(juju: jubilant.Juju, app_name: str):
    status = juju.status()
    units = sorted(status.apps[app_name].units)
    for unit in units:
        remove_transition_file(juju, unit)

    unit_a = units[3]
    unit_b = units[4]

    juju.run(unit_b, 'deferred-restart', {'delay': 10, 'max-retry': 1})
    juju.run(unit_a, 'failed-restart', {'delay': 1, 'max-retry': 2})
    for _ in range(3):
        juju.run(unit_a, 'restart', {'delay': 1})  # change to failed-restart

    juju.wait(
        lambda status: status.apps[app_name].units[unit_a].is_active,
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    unit_a_events = get_unit_events(juju, unit_a)
    relevant_events = [e['event'] for e in unit_a_events]

    logger.info('unit_a_events %s', unit_a_events)

    assert relevant_events == [
        'action:failed-restart',
        'action:restart',
        'action:restart',
        'action:restart',
        '_failed_restart:start',  # attempt 0
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 1
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 2
        '_failed_restart:retry_release',
        '_restart:start',
        '_restart:done',
    ], f'unexpected event sequence: {relevant_events}'


def test_retry_on_leader_unit_leaves_the_hook(juju: jubilant.Juju, app_name: str):
    status = juju.status()
    units = sorted(status.apps[app_name].units)
    for unit in units:
        remove_transition_file(juju, unit)

    leader = get_leader_unit_name(juju, app_name)
    non_leader = next(unit for unit in units if unit != leader)

    juju.run(leader, 'failed-restart', {'delay': 5})
    juju.run(non_leader, 'restart', {'delay': 3})

    juju.wait(
        lambda status: status.apps[app_name].units[non_leader].is_active,
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    non_leader_events = get_unit_events(juju, non_leader)
    relevant_events = [e['event'] for e in non_leader_events]

    assert relevant_events == [
        'action:restart',
        '_restart:start',
        '_restart:done',
    ], f'unexpected event sequence: {relevant_events}'
