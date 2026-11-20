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

"""Requirer charm for vault-kv integration tests."""

import secrets

import ops

from charmlibs.interfaces import vault_kv

NONCE_SECRET_LABEL = "vault-kv-nonce"
WAITING = ops.BlockedStatus("Waiting for vault-kv relation")


class RequirerCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.vault_kv = vault_kv.VaultKvRequires(self, "vault-kv", mount_suffix="test")
        framework.observe(self.on.install, self._on_install)
        framework.observe(self.vault_kv.on.connected, self._on_connected)
        framework.observe(self.vault_kv.on.ready, self._on_ready)
        framework.observe(self.vault_kv.on.gone_away, self._on_gone_away)
        framework.observe(self.on.get_credentials_action, self._on_get_credentials_action)

    def _on_install(self, event: ops.InstallEvent):
        self.unit.add_secret({"nonce": secrets.token_hex(16)}, label=NONCE_SECRET_LABEL)
        self.unit.status = WAITING

    def _on_connected(self, event: vault_kv.VaultKvConnectedEvent):
        binding = self.model.get_binding(event.relation)
        egress_subnets = [str(subnet) for subnet in binding.network.egress_subnets]
        nonce = self.model.get_secret(label=NONCE_SECRET_LABEL).get_content()["nonce"]
        self.vault_kv.request_credentials(event.relation, egress_subnets, nonce)

    def _on_ready(self, event: vault_kv.VaultKvReadyEvent):
        self.unit.status = ops.ActiveStatus()

    def _on_gone_away(self, event: vault_kv.VaultKvGoneAwayEvent):
        self.unit.status = WAITING

    def _on_get_credentials_action(self, event: ops.ActionEvent):
        relation = self.model.get_relation("vault-kv")
        if relation is None:
            event.fail("No vault-kv relation")
            return
        secret_id = self.vault_kv.get_unit_credentials(relation)
        if secret_id is None:
            event.fail("No credentials for this unit")
            return
        credentials = self.model.get_secret(id=secret_id).get_content(refresh=True)
        event.set_results({
            "vault-url": self.vault_kv.get_vault_url(relation),
            "ca-certificate": self.vault_kv.get_ca_certificate(relation),
            "mount": self.vault_kv.get_mount(relation),
            "role-id": credentials["role-id"],
            "role-secret-id": credentials["role-secret-id"],
        })


if __name__ == "__main__":
    ops.main(RequirerCharm)
