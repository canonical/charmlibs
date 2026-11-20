#!/usr/bin/env python3
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

"""Provider charm for vault-kv integration tests.

Mirrors how the Vault charm answers requests, but publishes synthetic
credentials instead of creating AppRoles in a real Vault server.
"""

import ops

from charmlibs.interfaces import vault_kv

VAULT_URL = "https://vault.example.com:8200"
CA_CERTIFICATE = "test-ca-certificate"


class ProviderCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.vault_kv = vault_kv.VaultKvProvides(self, "vault-kv")
        framework.observe(self.on.install, self._on_install)
        framework.observe(self.vault_kv.on.new_vault_kv_client_attached, self._on_attached)
        framework.observe(self.vault_kv.on.vault_kv_client_detached, self._on_detached)

    def _on_install(self, event: ops.InstallEvent):
        self.unit.status = ops.ActiveStatus()

    def _on_attached(self, event: vault_kv.NewVaultKvClientAttachedEvent):
        if not self.unit.is_leader():
            return
        unit = event.unit_name.replace("/", "-")
        label = f"vault-kv-{unit}"
        try:
            secret = self.model.get_secret(label=label)
        except ops.SecretNotFoundError:
            content = {"role-id": f"role-{unit}", "role-secret-id": f"secret-{unit}"}
            secret = self.app.add_secret(content, label=label)
        secret.grant(event.relation)
        secret_id = secret.get_info().id
        self.vault_kv.set_kv_data(
            relation=event.relation,
            mount=f"charm-{event.app_name}-{event.mount_suffix}",
            ca_certificate=CA_CERTIFICATE,
            vault_url=VAULT_URL,
            nonce=event.nonce,
            credentials_juju_secret_id=secret_id,
        )

    def _on_detached(self, event: vault_kv.VaultKvClientDetachedEvent):
        self.unit.status = ops.ActiveStatus(f"detached {event.unit_name}")


if __name__ == "__main__":
    ops.main(ProviderCharm)
