# Copyright 2025 Canonical Ltd.
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

import json
import logging
from datetime import datetime

import jubilant
from tenacity import retry, stop_after_delay, wait_fixed

TRACE_FILE = '/var/lib/charm-rolling-ops/transitions.log'
logger = logging.getLogger(__name__)


@retry(wait=wait_fixed(10), stop=stop_after_delay(60), reraise=True)
def wait_for_etcdctl_env(juju: jubilant.Juju, unit: str) -> None:
    task = juju.exec('test -f /var/lib/rollingops/etcd/etcdctl.env', unit=unit)
    if task.status != 'completed' or task.return_code != 0:
        raise RuntimeError('etcdctl env file not ready')


def get_unit_events(juju: jubilant.Juju, unit: str) -> list[dict[str, str]]:
    task = juju.exec(f'cat {TRACE_FILE}', unit=unit)

    if not task.stdout.strip():
        return []

    return [json.loads(line) for line in task.stdout.strip().splitlines()]


def parse_ts(event: dict[str, str]) -> datetime:
    return datetime.fromisoformat(event['ts'])


def test_deploy(juju: jubilant.Juju, charm: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert charm in juju.status().apps


def test_restart_action_one_unit(juju: jubilant.Juju, charm: str):
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

    juju.integrate(
        'etcd:client-certificates',
        'self-signed-certificates:certificates',
    )
    juju.wait(jubilant.all_active, error=jubilant.any_error)

    juju.integrate(f'{charm}:etcd', 'etcd:etcd-client')
    juju.wait(jubilant.all_active, error=jubilant.any_error)

    wait_for_etcdctl_env(juju, f'{charm}/0')

    juju.run(f'{charm}/0', 'restart', {'delay': 1}, wait=300)

    juju.wait(
        jubilant.all_active,
        error=jubilant.any_error,
        timeout=300,
    )

    events = get_unit_events(juju, f'{charm}/0')
    restart_events = [e['event'] for e in events]

    expected = [
        'action:restart',
        '_restart:start',
        '_restart:done',
    ]

    assert expected == restart_events


def test_all_units_can_connect_to_etcd(juju: jubilant.Juju, charm: str):
    juju.add_unit(charm, num_units=2)
    juju.wait(
        lambda status: jubilant.all_active(status, charm),
        error=jubilant.any_error,
    )

    status = juju.status()
    units = sorted(status.apps[charm].units)

    for unit in units:
        juju.exec(f'rm -f {TRACE_FILE}', unit=unit)

    for unit in units:
        juju.run(unit, 'restart', {'delay': 2}, wait=300)

    juju.wait(
        lambda status: jubilant.all_active(status, charm, 'etcd', 'self-signed-certificates'),
        error=jubilant.any_error,
        timeout=600,
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
