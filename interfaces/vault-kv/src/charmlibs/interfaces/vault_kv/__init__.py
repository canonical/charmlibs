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

"""Library for the vault-kv relation.

This library contains the Requires and Provides classes for handling the vault-kv
interface.

Getting Started
---------------
From a charm directory, add the library package:

.. code-block:: console

    uv add charmlibs-interfaces-vault-kv

Requirer charm
--------------
The requirer charm is the charm requiring a secret value store. In this example, the requirer charm
is requiring a secret value store.

.. code-block:: python

    import secrets

    from charmlibs.interfaces import vault_kv
    from ops.charm import CharmBase, InstallEvent
    from ops.main import main
    from ops.model import ActiveStatus, BlockedStatus

    NONCE_SECRET_LABEL = "nonce"


    class ExampleRequirerCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.interface = vault_kv.VaultKvRequires(
                self,
                "vault-kv",
                "my-suffix",
            )

            self.framework.observe(self.on.install, self._on_install)
            self.framework.observe(self.interface.on.connected, self._on_connected)
            self.framework.observe(self.interface.on.ready, self._on_ready)
            self.framework.observe(self.interface.on.gone_away, self._on_gone_away)
            self.framework.observe(self.on.update_status, self._on_update_status)

        def _on_install(self, event: InstallEvent):
            self.unit.add_secret(
                {"nonce": secrets.token_hex(16)},
                label=NONCE_SECRET_LABEL,
                description="Nonce for vault-kv relation",
            )
            self.unit.status = BlockedStatus("Waiting for vault-kv relation")

        def _on_connected(self, event: vault_kv.VaultKvConnectedEvent):
            relation = self.model.get_relation(event.relation_name, event.relation_id)
            egress_subnets = [str(subnet) for subnet in self.model.get_binding(relation).network.egress_subnets]
            egress_subnets.append(str(self.model.get_binding(relation).network.interfaces[0].subnet))
            self.interface.request_credentials(relation, egress_subnets, self.get_nonce())

        def _on_ready(self, event: vault_kv.VaultKvReadyEvent):
            relation = self.model.get_relation(event.relation_name, event.relation_id)
            if relation is None:
                return
            vault_url = self.interface.get_vault_url(relation)
            ca_certificate = self.interface.get_ca_certificate(relation)
            mount = self.interface.get_mount(relation)

            unit_credentials = self.interface.get_unit_credentials(relation)
            # unit_credentials is a juju secret id
            secret = self.model.get_secret(id=unit_credentials)
            secret_content = secret.get_content(refresh=True)
            role_id = secret_content["role-id"]
            role_secret_id = secret_content["role-secret-id"]

            self._configure(vault_url, ca_certificate, mount, role_id, role_secret_id)

            self.unit.status = ActiveStatus()

        def _on_gone_away(self, event: vault_kv.VaultKvGoneAwayEvent):
            self.unit.status = BlockedStatus("Waiting for vault-kv relation")

        def _configure(
            self,
            vault_url: str,
            ca_certificate: str,
            mount: str,
            role_id: str,
            role_secret_id: str,
        ):
            pass

        def _on_update_status(self, event):
            # Check somewhere that egress subnet has not changed i.e. pod has not been rescheduled
            # Update status might not be the best place
            binding = self.model.get_binding("vault-kv")
            if binding is not None:
                relation = self.model.get_relation(relation_name="vault-kv")
                egress_subnets = [str(subnet) for subnet in self.model.get_binding(relation).network.egress_subnets]
                egress_subnets.append(str(self.model.get_binding(relation).network.interfaces[0].subnet))
                self.interface.request_credentials(relation, egress_subnets, self.get_nonce())

        def get_nonce(self):
            secret = self.model.get_secret(label=NONCE_SECRET_LABEL)
            nonce = secret.get_content(refresh=True)["nonce"]
            return nonce


    if __name__ == "__main__":
        main(ExampleRequirerCharm)

You can integrate both charms by running:

.. code-block:: console

    juju integrate <vault provider charm> <vault requirer charm>
"""

from ._vault_kv import (
    AppVaultKvRequirerSchema,
    KVRequest,
    LogAdapter,
    NewVaultKvClientAttachedEvent,
    ProviderSchema,
    RequirerSchema,
    UnitVaultKvRequirerSchema,
    VaultKvBaseEvent,
    VaultKvClientDetachedEvent,
    VaultKvConnectedEvent,
    VaultKvGoneAwayEvent,
    VaultKvProviderEvents,
    VaultKvProviderSchema,
    VaultKvProvides,
    VaultKvReadyEvent,
    VaultKvRequireEvents,
    VaultKvRequires,
    get_egress_subnets_list_from_relation_data,
    is_provider_data_valid,
    is_requirer_data_valid,
)
from ._version import __version__ as __version__

__all__ = [
    "AppVaultKvRequirerSchema",
    "KVRequest",
    "LogAdapter",
    "NewVaultKvClientAttachedEvent",
    "ProviderSchema",
    "RequirerSchema",
    "UnitVaultKvRequirerSchema",
    "VaultKvBaseEvent",
    "VaultKvClientDetachedEvent",
    "VaultKvConnectedEvent",
    "VaultKvGoneAwayEvent",
    "VaultKvProviderEvents",
    "VaultKvProviderSchema",
    "VaultKvProvides",
    "VaultKvReadyEvent",
    "VaultKvRequireEvents",
    "VaultKvRequires",
    "get_egress_subnets_list_from_relation_data",
    "is_provider_data_valid",
    "is_requirer_data_valid",
]
