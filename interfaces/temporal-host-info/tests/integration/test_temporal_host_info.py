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

import jubilant


def test_deploy(juju: jubilant.Juju, provider: str, requirer: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert provider in juju.status().apps
    assert requirer in juju.status().apps


def test_integrate(juju: jubilant.Juju, provider: str, requirer: str):
    """Test that the relation is established."""
    hostname = 'temporal.server.local'
    juju.config(provider, {'external-hostname': hostname})
    juju.integrate(f'{provider}:temporal-host-info', f'{requirer}:temporal-host-info')
    juju.wait(jubilant.all_active)
    status = juju.status()
    assert (
        status.apps[requirer].units[f'{requirer}/0'].workload_status.message
        == f'Temporal host: {hostname}, port: 7233'
    )


def test_config_changed(juju: jubilant.Juju, provider: str, requirer: str):
    """Test that changing the provider config updates the requirer status."""
    new_hostname = 'new.temporal.server.local'
    juju.config(provider, {'external-hostname': new_hostname})
    juju.wait(jubilant.all_active)
    status = juju.status()
    assert (
        status.apps[requirer].units[f'{requirer}/0'].workload_status.message
        == f'Temporal host: {new_hostname}, port: 7233'
    )
