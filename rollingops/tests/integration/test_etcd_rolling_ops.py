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
from pathlib import Path

import jubilant
import pytest
from tenacity import retry, stop_after_delay, wait_fixed

from tests.integration.utils import (
    get_unit_events,
    is_empty_file,
    parse_ts,
    remove_transition_file,
)

logger = logging.getLogger(__name__)
TIMEOUT = 15 * 60.0
ETCD_PROCESS_LOGS = '/var/log/etcd_rollingops_worker.log'
PEER_PROCCES_LOGS = '/var/log/peer_rollingops_worker.log'
ETCD_CONFIG_FILE = '/var/lib/rollingops/etcd/etcdctl.json'


def etcdctl_file_exits(juju: jubilant.Juju, unit: str) -> bool:
    task = juju.exec(f'test -f {ETCD_CONFIG_FILE}', unit=unit)
    if task.status != 'completed' or task.return_code != 0:
        return False
    return True


@retry(wait=wait_fixed(10), stop=stop_after_delay(60), reraise=True)
def wait_for_etcdctl_config_file(juju: jubilant.Juju, unit: str) -> None:
    if not etcdctl_file_exits(juju, unit):
        raise RuntimeError('etcdctl config file not ready')


def test_deploy(juju: jubilant.Juju, app_name: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert app_name in juju.status().apps


@pytest.mark.machine_only
def test_charm_is_integrated_with_etcd(juju: jubilant.Juju, app_name: str):
    juju.deploy(
        'self-signed-certificates',
        app='self-signed-certificates',
        channel='1/stable',
    )
    juju.deploy(
        'charmed-etcd',
        app='etcd',
        channel='3.6/stable',
    )
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    juju.integrate(
        'etcd:client-certificates',
        'self-signed-certificates:certificates',
    )
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    juju.integrate(f'{app_name}:etcd', 'etcd:etcd-client')
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    wait_for_etcdctl_config_file(juju, f'{app_name}/0')


@pytest.mark.machine_only
def test_restart_action_one_unit_single_app(juju: jubilant.Juju, app_name: str):
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
    assert not is_empty_file(juju, unit, ETCD_PROCESS_LOGS)
    assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_failed_restart_retries_one_unit_single_app(juju: jubilant.Juju, app_name: str):
    unit = f'{app_name}/0'
    remove_transition_file(juju, unit)

    juju.run(unit, 'failed-restart', {'delay': 1, 'max-retry': 1})
    juju.run(unit, 'restart', {'delay': 1})
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    events = get_unit_events(juju, unit)
    restart_events = [e['event'] for e in events if not e['event'].startswith('action')]

    expected = [
        '_failed_restart:start',  # attempt 0
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 1
        '_failed_restart:retry_release',
        '_restart:start',
        '_restart:done',
    ]
    assert restart_events == expected, f'unexpected event order: {restart_events}'
    assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_assert_deferred_restart_retries_one_unit_single_app(juju: jubilant.Juju, app_name: str):
    unit = f'{app_name}/0'
    remove_transition_file(juju, unit)

    juju.run(unit, 'deferred-restart', {'delay': 1, 'max-retry': 1}, wait=TIMEOUT)
    juju.run(unit, 'restart', {'delay': 1})
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    events = get_unit_events(juju, unit)
    restart_events = [e['event'] for e in events if not e['event'].startswith('action')]

    expected = [
        '_deferred_restart:start',  # attempt 0
        '_deferred_restart:retry_hold',
        '_deferred_restart:start',  # retry 1
        '_deferred_restart:retry_hold',
        '_restart:start',
        '_restart:done',
    ]
    assert restart_events == expected, f'unexpected event order: {restart_events}'
    assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_assert_restart_rolls_one_unit_at_a_time_single_app(juju: jubilant.Juju, app_name: str):
    juju.add_unit(app=app_name, num_units=4)
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    status = juju.status()
    units = sorted(status.apps[app_name].units)
    for unit in units:
        remove_transition_file(juju, unit)

    for unit in units:
        juju.run(unit, 'restart', {'delay': 15})
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    all_events: list[dict[str, str]] = []
    for unit in units:
        events = get_unit_events(juju, unit)
        assert len(events) == 3
        all_events.extend(events)

    restart_events = [e for e in all_events if not e['event'].startswith('action')]
    restart_events.sort(key=parse_ts)

    logger.info(restart_events)

    assert len(restart_events) == len(units) * 2
    for i in range(0, len(restart_events), 2):
        start_event = restart_events[i]
        done_event = restart_events[i + 1]

        assert start_event['event'] == '_restart:start'
        assert done_event['event'] == '_restart:done'
        assert start_event['unit'] == done_event['unit'], (
            f'start/done pair mismatch: {start_event} vs {done_event}'
        )
    for unit in units:
        assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_retry_hold_operation_two_units_single_app(juju: jubilant.Juju, app_name: str):
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

    relevant_events = [e for e in all_events if not e['event'].startswith('action')]
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

    for unit in units:
        assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_retry_release_two_units_single_app(juju: jubilant.Juju, app_name: str):
    status = juju.status()
    units = sorted(status.apps[app_name].units)
    for unit in units:
        remove_transition_file(juju, unit)

    unit_a = units[2]
    unit_b = units[4]

    juju.run(unit_a, 'failed-restart', {'delay': 10, 'max-retry': 2}, wait=TIMEOUT)
    juju.run(unit_b, 'failed-restart', {'delay': 15, 'max-retry': 2}, wait=TIMEOUT)

    time.sleep(
        60 * 2
    )  # wait for operation execution. TODO: in charm use lock state to clear status.

    all_events: list[dict[str, str]] = []
    all_events.extend(get_unit_events(juju, unit_a))
    all_events.extend(get_unit_events(juju, unit_b))
    all_events.sort(key=parse_ts)

    restart_events = [e for e in all_events if not e['event'].startswith('action')]
    restart_events.sort(key=parse_ts)

    logger.info(restart_events)

    assert len(restart_events) == 2 * 2 * 3  # 2 units * 2 events * 3 executions
    for i in range(0, len(restart_events), 2):
        start_event = restart_events[i]
        done_event = restart_events[i + 1]

        assert start_event['event'] == '_failed_restart:start'
        assert done_event['event'] == '_failed_restart:retry_release'
        assert start_event['unit'] == done_event['unit'], (
            f'start/done pair mismatch: {start_event} vs {done_event}'
        )
    for unit in units:
        assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_subsequent_lock_request_ops_single_app(juju: jubilant.Juju, app_name: str):
    status = juju.status()
    units = sorted(status.apps[app_name].units)
    for unit in units:
        remove_transition_file(juju, unit)

    unit_a = units[3]

    juju.run(unit_a, 'failed-restart', {'delay': 1, 'max-retry': 1})
    for _ in range(3):
        juju.run(unit_a, 'deferred-restart', {'delay': 1, 'max-retry': 0})
    juju.run(unit_a, 'restart', {'delay': 1})

    juju.wait(
        lambda status: status.apps[app_name].units[unit_a].is_active,
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    unit_a_events = get_unit_events(juju, unit_a)
    relevant_events = [e['event'] for e in unit_a_events if not e['event'].startswith('action')]
    logger.info('unit_a_events %s', unit_a_events)

    assert relevant_events == [
        '_failed_restart:start',  # attempt 0
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 1
        '_failed_restart:retry_release',
        '_deferred_restart:start',  # attempt 0
        '_deferred_restart:retry_hold',
        '_restart:start',
        '_restart:done',
    ], f'unexpected event sequence: {relevant_events}'

    for unit in units:
        assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_rolling_ops_multi_app(juju: jubilant.Juju, charm: Path, app_name: str):
    second_app = f'{app_name}-secondary'
    juju.deploy(charm, app=second_app, num_units=3)
    juju.wait(
        lambda status: jubilant.all_active(status, second_app),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )
    juju.integrate(f'{second_app}:etcd', 'etcd:etcd-client')

    juju.wait(
        lambda status: jubilant.all_active(status, second_app, 'etcd'),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    primary_units = sorted(juju.status().apps[app_name].units.keys())
    secondary_units = sorted(juju.status().apps[second_app].units.keys())
    all_units: list[str] = primary_units + secondary_units

    for unit in all_units:
        remove_transition_file(juju, unit)
        wait_for_etcdctl_config_file(juju, unit)

    for unit in all_units:
        juju.run(unit, 'restart', {'delay': 10}, wait=TIMEOUT)

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    all_events: list[dict[str, str]] = []

    for unit in all_units:
        events = get_unit_events(juju, unit)
        assert len(events) == 3
        all_events.extend(events)

    restart_events = [e for e in all_events if not e['event'].startswith('action')]
    restart_events.sort(key=parse_ts)

    logger.info(restart_events)

    assert len(restart_events) == len(all_units) * 2
    for i in range(0, len(restart_events), 2):
        start_event = restart_events[i]
        done_event = restart_events[i + 1]

        assert start_event['event'] == '_restart:start'
        assert done_event['event'] == '_restart:done'
        assert start_event['unit'] == done_event['unit'], (
            f'start/done pair mismatch: {start_event} vs {done_event}'
        )
    for unit in all_units:
        assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_rolling_ops_sync_lock_multi_app(juju: jubilant.Juju, app_name: str):
    second_app = f'{app_name}-secondary'
    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    primary_units = sorted(juju.status().apps[app_name].units.keys())
    secondary_units = sorted(juju.status().apps[second_app].units.keys())
    all_units: list[str] = primary_units + secondary_units

    for unit in all_units:
        remove_transition_file(juju, unit)
        wait_for_etcdctl_config_file(juju, unit)

    unit_a = primary_units[1]
    unit_b = secondary_units[1]

    juju.cli('run', unit_a, 'sync-restart', 'delay=15', '--background')
    time.sleep(2)
    juju.cli('run', unit_b, 'sync-restart', 'delay=15', '--background')

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    all_events: list[dict[str, str]] = []

    for unit in {unit_a, unit_b}:
        events = get_unit_events(juju, unit)
        assert len(events) == 3
        all_events.extend(events)

    all_events.sort(key=parse_ts)
    restart_events = [
        (e['unit'], e['event']) for e in all_events if not e['event'].startswith('action')
    ]

    logger.info(restart_events)

    assert restart_events == [
        (unit_a, '_sync_restart:start'),
        (unit_a, '_sync_restart:done'),
        (unit_b, '_sync_restart:start'),
        (unit_b, '_sync_restart:done'),
    ], f'unexpected event sequence: {restart_events}'

    for unit in all_units:
        assert is_empty_file(juju, unit, PEER_PROCCES_LOGS)


@pytest.mark.machine_only
def test_lock_released_when_unit_removed(juju: jubilant.Juju, app_name: str) -> None:
    units = sorted(juju.status().apps[app_name].units.keys())
    for unit in units:
        remove_transition_file(juju, unit)
    unit_a = units[1]
    unit_b = units[2]

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    juju.run(unit_a, 'deferred-restart', {'delay': 15})
    time.sleep(5)
    juju.run(unit_b, 'restart', {'delay': 2})

    juju.remove_unit(unit_a)

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    unit_b_events = get_unit_events(juju, unit_b)
    relevant_events = [e['event'] for e in unit_b_events if not e['event'].startswith('action')]

    logger.info('unit_b_events %s', unit_b_events)

    assert relevant_events == [
        '_restart:start',
        '_restart:done',
    ], f'unexpected event sequence: {relevant_events}'


@pytest.mark.machine_only
def test_actions_still_work_after_etcd_relation_removed(
    juju: jubilant.Juju, app_name: str
) -> None:
    units = sorted(juju.status().apps[app_name].units.keys())
    for unit in units:
        remove_transition_file(juju, unit)

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    unit_a = units[3]

    juju.run(unit_a, 'failed-restart', {'delay': 10, 'max-retry': 2})
    for i in range(3):
        juju.run(unit_a, 'restart', {'delay': i})

    juju.remove_relation(f'{app_name}:etcd', 'etcd:etcd-client')

    juju.wait(jubilant.all_active, error=jubilant.any_error, timeout=TIMEOUT)

    unit_a_events = get_unit_events(juju, unit_a)
    relevant_events = [e['event'] for e in unit_a_events if not e['event'].startswith('action')]

    logger.info('unit_a_events %s', unit_a_events)

    assert relevant_events == [
        '_failed_restart:start',  # attempt 0
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 1
        '_failed_restart:retry_release',
        '_failed_restart:start',  # retry 2
        '_failed_restart:retry_release',
        '_restart:start',
        '_restart:done',
        '_restart:start',
        '_restart:done',
        '_restart:start',
        '_restart:done',
    ], f'unexpected event sequence: {relevant_events}'
