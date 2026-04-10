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
from pathlib import Path

import jubilant
import pytest
from tenacity import retry, stop_after_delay, wait_fixed

from tests.integration.utils import get_unit_events, remove_transition_file

TRACE_FILE = '/var/lib/charm-rolling-ops/transitions.log'
logger = logging.getLogger(__name__)
TIMEOUT = 15 * 60.0


@retry(wait=wait_fixed(10), stop=stop_after_delay(60), reraise=True)
def wait_for_etcdctl_env(juju: jubilant.Juju, unit: str) -> None:
    task = juju.exec('test -f /var/lib/rollingops/etcd/etcdctl.json', unit=unit)
    if task.status != 'completed' or task.return_code != 0:
        raise RuntimeError('etcdctl config file not ready')


def test_deploy(juju: jubilant.Juju, app_name: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert app_name in juju.status().apps


@pytest.mark.machine_only
def test_restart_action_one_unit(juju: jubilant.Juju, app_name: str):
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

    wait_for_etcdctl_env(juju, f'{app_name}/0')

    juju.run(f'{app_name}/0', 'restart', {'delay': 1}, wait=300)

    juju.wait(
        jubilant.all_active,
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    events = get_unit_events(juju, f'{app_name}/0')
    restart_events = [e['event'] for e in events]

    expected = [
        'action:restart',
        '_restart:start',
        '_restart:done',
    ]

    assert expected == restart_events


@pytest.mark.machine_only
def test_all_units_can_connect_to_etcd(juju: jubilant.Juju, app_name: str):
    juju.add_unit(app_name, num_units=2)
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    status = juju.status()
    units = sorted(status.apps[app_name].units)

    for unit in units:
        remove_transition_file(juju, unit)

    for unit in units:
        juju.run(unit, 'restart', {'delay': 2}, wait=300)

    juju.wait(
        lambda status: jubilant.all_active(status, app_name, 'etcd', 'self-signed-certificates'),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    expected = [
        'action:restart',
        '_restart:start',
        '_restart:done',
    ]

    for unit in units:
        events = get_unit_events(juju, unit)
        restart_events = [e['event'] for e in events]
        assert restart_events == expected


@pytest.mark.machine_only
def test_all_units_can_connect_to_etcd_multi_app(juju: jubilant.Juju, charm: Path, app_name: str):
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
        wait_for_etcdctl_env(juju, unit)

    for unit in all_units:
        juju.run(unit, 'restart', {'delay': 2}, wait=300)

    juju.wait(
        lambda status: jubilant.all_active(
            status,
            app_name,
            second_app,
            'etcd',
            'self-signed-certificates',
        ),
        error=jubilant.any_error,
        timeout=TIMEOUT,
    )

    expected = [
        'action:restart',
        '_restart:start',
        '_restart:done',
    ]

    for unit in all_units:
        events = get_unit_events(juju, unit)
        restart_events = [e['event'] for e in events]
        assert restart_events == expected
