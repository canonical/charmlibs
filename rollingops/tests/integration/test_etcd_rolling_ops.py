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

import jubilant
import pytest
from tenacity import retry, stop_after_delay, wait_fixed

from tests.integration.shared_tests import (
    assert_deferred_restart_retries_one_unit,
    assert_failed_restart_retries_one_unit,
    assert_restart_action_one_unit,
    assert_restart_rolls_one_unit_at_a_time,
    assert_retry_hold_keeps_lock_on_same_unit,
    assert_subsequent_lock_request_of_different_ops,
    assert_subsequent_lock_request_of_same_op,
)

logger = logging.getLogger(__name__)
TIMEOUT = 15 * 60.0


def test_deploy(juju: jubilant.Juju, app_name: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert app_name in juju.status().apps


@retry(wait=wait_fixed(10), stop=stop_after_delay(60), reraise=True)
def wait_for_etcdctl_config_file(juju: jubilant.Juju, unit: str) -> None:
    task = juju.exec('test -f /var/lib/rollingops/etcd/etcdctl.json', unit=unit)
    if task.status != 'completed' or task.return_code != 0:
        raise RuntimeError('etcdctl config file not ready')


@pytest.mark.machine_only
def test_etcdctl_config_file_is_created(juju: jubilant.Juju, app_name: str):
    """Verify that restart action runs through the expected workflow."""

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
    assert_restart_action_one_unit(juju, app_name)


@pytest.mark.machine_only
def test_failed_restart_retries_one_unit_single_app(juju: jubilant.Juju, app_name: str):
    assert_failed_restart_retries_one_unit(juju, app_name)


@pytest.mark.machine_only
def test_assert_deferred_restart_retries_one_unit_single_app(juju: jubilant.Juju, app_name: str):
    assert_deferred_restart_retries_one_unit(juju, app_name)


@pytest.mark.machine_only
def test_assert_restart_rolls_one_unit_at_a_time_single_app(juju: jubilant.Juju, app_name: str):
    assert_restart_rolls_one_unit_at_a_time(juju, app_name)


@pytest.mark.machine_only
def test_retry_hold_keeps_lock_on_same_unit_single_app(juju: jubilant.Juju, app_name: str):
    assert_retry_hold_keeps_lock_on_same_unit(juju, app_name)


"""
@pytest.mark.machine_only
def test_retry_release_single_app(juju: jubilant.Juju, app_name: str):
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

    all_events: list[dict[str, str]] = []

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
"""


@pytest.mark.machine_only
def test_subsequent_lock_request_of_different_ops_single_app(juju: jubilant.Juju, app_name: str):
    assert_subsequent_lock_request_of_different_ops(juju, app_name)


@pytest.mark.machine_only
def test_subsequent_lock_request_of_same_op_single_app(juju: jubilant.Juju, app_name: str):
    assert_subsequent_lock_request_of_same_op(juju, app_name)


"""
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
        lambda status: jubilant.all_active(
            status, app_name, second_app, 'etcd', 'self-signed-certificates'
        ),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    primary_units = sorted(juju.status().apps[app_name].units.keys())
    secondary_units = sorted(juju.status().apps[second_app].units.keys())
    all_units: list[str] = primary_units + secondary_units

    for unit in all_units:
        remove_transition_file(juju, unit)

    for unit in all_units:
        wait_for_etcdctl_config_file(juju, unit)

    for unit in all_units:
        juju.run(unit, 'restart', {'delay': 2}, wait=TIMEOUT)

    juju.wait(
        lambda status: jubilant.all_active(status, app_name, second_app),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    all_events: list[dict[str, str]] = []

    for unit in all_units:
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
"""
