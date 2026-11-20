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

"""Integration tests for the vault-kv library, using test charms in place of Vault."""

import pathlib

import jubilant

PACKED_DIR = pathlib.Path(__file__).parent / ".packed"
PROVIDER = "provider"
REQUIRER = "requirer"


def test_requirer_receives_credentials_then_relation_is_removed(juju: jubilant.Juju):
    juju.deploy(PACKED_DIR / "provider.charm", app=PROVIDER)
    juju.deploy(PACKED_DIR / "requirer.charm", app=REQUIRER)
    juju.integrate(PROVIDER, REQUIRER)
    juju.wait(jubilant.all_active, error=jubilant.any_error)

    task = juju.run(f"{REQUIRER}/0", "get-credentials")
    assert task.results == {
        "vault-url": "https://vault.example.com:8200",
        "ca-certificate": "test-ca-certificate",
        "mount": f"charm-{REQUIRER}-test",
        "role-id": f"role-{REQUIRER}-0",
        "role-secret-id": f"secret-{REQUIRER}-0",
    }

    juju.remove_relation(PROVIDER, REQUIRER)
    juju.wait(
        lambda status: (
            jubilant.all_blocked(status, REQUIRER)
            and status.apps[PROVIDER].units[f"{PROVIDER}/0"].workload_status.message
            == f"detached {REQUIRER}/0"
        ),
        error=jubilant.any_error,
    )
