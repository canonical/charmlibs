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

logger = logging.getLogger(__name__)
TIMEOUT = 15 * 60.0


def test_deploy(juju: jubilant.Juju, app_name: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert app_name in juju.status().apps


"""
def test_restart_action_one_unit(juju: jubilant.Juju, app_name: str):
    assert_restart_action_one_unit(juju, app_name)


def test_failed_restart_retries_one_unit(juju: jubilant.Juju, app_name: str):
    assert_failed_restart_retries_one_unit(juju, app_name)


def test_assert_deferred_restart_retries_one_unit(juju: jubilant.Juju, app_name: str):
    assert_deferred_restart_retries_one_unit(juju, app_name)


def test_assert_restart_rolls_one_unit_at_a_time(juju: jubilant.Juju, app_name: str):
    assert_restart_rolls_one_unit_at_a_time(juju, app_name)


def test_retry_hold_keeps_lock_on_same_unit(juju: jubilant.Juju, app_name: str):
    assert_retry_hold_keeps_lock_on_same_unit(juju, app_name)


def test_retry_release_alternates_execution(juju: jubilant.Juju, app_name: str):
    assert_retry_release_alternates_execution(juju, app_name)


def test_subsequent_lock_request_of_different_ops(juju: jubilant.Juju, app_name: str):
    assert_subsequent_lock_request_of_different_ops(juju, app_name)


def test_subsequent_lock_request_of_same_op(juju: jubilant.Juju, app_name: str):
    assert_subsequent_lock_request_of_same_op(juju, app_name)


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
"""
