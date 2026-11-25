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

"""Implementation migrated from charms.vault_k8s.v0.vault_kv (LIBAPI 0, LIBPATCH 16)."""

import json
import logging
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

import ops
from pydantic import BaseModel, Field, Json, ValidationError


class LogAdapter(logging.LoggerAdapter):  # pyright: ignore[reportMissingTypeArgument]
    """Adapter for the logger to prepend a prefix to all log lines."""

    prefix = "vault_kv"

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        """Decides the format for the prepended text."""
        return f"[{self.prefix}] {msg}", kwargs


logger = LogAdapter(logging.getLogger(__name__), {})


class VaultKvProviderSchema(BaseModel):
    """Provider side of the vault-kv interface."""

    vault_url: str = Field(description="The URL of the Vault server to connect to.")
    mount: str = Field(
        description=(
            "The KV mount available for the requirer application, "
            "respecting the pattern 'charm-<requirer app>-<user provided suffix>'."
        )
    )
    ca_certificate: str = Field(
        description="The CA certificate to use when validating the Vault server's certificate."
    )
    credentials: Json[Mapping[str, str]] = Field(
        description=(
            "Mapping of unit name and credentials for that unit."
            " Credentials are a juju secret containing a 'role-id' and a 'role-secret-id'."
        )
    )


class AppVaultKvRequirerSchema(BaseModel):
    """App schema of the requirer side of the vault-kv interface."""

    mount_suffix: str = Field(
        description="Suffix to append to the mount name to get the KV mount."
    )


class UnitVaultKvRequirerSchema(BaseModel):
    """Unit schema of the requirer side of the vault-kv interface."""

    egress_subnet: str = Field(
        description="Egress subnets to use separated by commas, in CIDR notation."
    )
    nonce: str = Field(
        description=(
            "Uniquely identifying value for this unit. `secrets.token_hex(16)` is recommended."
        )
    )


@dataclass
class KVRequest:
    """This class represents a kv request from an interface Requirer."""

    relation: ops.Relation
    app_name: str
    unit_name: str
    mount_suffix: str
    egress_subnets: list[str]
    nonce: str


def get_egress_subnets_list_from_relation_data(relation_databag: Mapping[str, str]) -> list[str]:
    """Return the egress_subnet as a list.

    This function converts the string with values separated by commas to a list.

    Args:
        relation_databag: the relation databag of the unit or the app.
    """
    return [subnet.strip() for subnet in relation_databag.get("egress_subnet", "").split(",")]


def is_requirer_data_valid(app_data: Mapping[str, str], unit_data: Mapping[str, str]) -> bool:
    """Return whether the requirer data is valid."""
    try:
        AppVaultKvRequirerSchema(**app_data)
        UnitVaultKvRequirerSchema(**unit_data)
        return True
    except ValidationError as e:
        logger.debug("Invalid data: %s", e)
        return False


def is_provider_data_valid(data: Mapping[str, str]) -> bool:
    """Return whether the provider data is valid."""
    try:
        VaultKvProviderSchema(**data)  # pyright: ignore[reportArgumentType]
        return True
    except ValidationError as e:
        logger.debug("Invalid data: %s", e)
        return False


class VaultKvGoneAwayEvent(ops.EventBase):
    """VaultKvGoneAwayEvent Event."""

    pass


class VaultKvClientDetachedEvent(ops.EventBase):
    """VaultKvClientDetachedEvent Event."""

    def __init__(self, handle: ops.Handle, unit_name: str):
        super().__init__(handle)
        self.unit_name = unit_name

    def snapshot(self) -> dict[str, Any]:
        """Return snapshot data that should be persisted."""
        return {
            "unit_name": self.unit_name,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore the event from a snapshot."""
        super().restore(snapshot)
        self.unit_name = snapshot["unit_name"]


class NewVaultKvClientAttachedEvent(ops.RelationEvent):
    """New vault kv client attached event."""

    def __init__(
        self,
        handle: ops.Handle,
        relation: ops.Relation,
        app_name: str,
        unit_name: str,
        mount_suffix: str,
        egress_subnets: list[str],
        nonce: str,
    ):
        super().__init__(handle, relation)
        self.relation_id = relation.id
        self.relation_name = relation.name
        self.app_name = app_name
        self.unit_name = unit_name
        self.mount_suffix = mount_suffix
        self.egress_subnets = egress_subnets
        self.nonce = nonce

    def snapshot(self) -> dict[str, Any]:
        """Return snapshot data that should be persisted."""
        return {
            "relation_id": self.relation_id,
            "relation_name": self.relation_name,
            "app_name": self.app_name,
            "unit_name": self.unit_name,
            "mount_suffix": self.mount_suffix,
            "egress_subnets": self.egress_subnets,
            "nonce": self.nonce,
        }

    def restore(self, snapshot: dict[str, Any]):
        """Restore the value state from a given snapshot."""
        super().restore(snapshot)
        self.relation_id = snapshot["relation_id"]
        self.app_name = snapshot["app_name"]
        self.unit_name = snapshot["unit_name"]
        self.mount_suffix = snapshot["mount_suffix"]
        self.egress_subnets = snapshot["egress_subnets"]
        self.nonce = snapshot["nonce"]


class VaultKvProviderEvents(ops.ObjectEvents):
    """List of events that the Vault Kv provider charm can leverage."""

    new_vault_kv_client_attached = ops.EventSource(NewVaultKvClientAttachedEvent)
    vault_kv_client_detached = ops.EventSource(VaultKvClientDetachedEvent)


class VaultKvProvides(ops.Object):
    """Class to be instantiated by the providing side of the relation."""

    on = VaultKvProviderEvents()

    def __init__(
        self,
        charm: ops.CharmBase,
        relation_name: str,
    ) -> None:
        self.charm = charm
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_departed,
            self._on_vault_kv_relation_departed,
        )

    def _on_relation_changed(self, event: ops.RelationChangedEvent):
        """Handle client changed relation.

        This handler will emit a new_vault_kv_client_attached event for each requiring unit
        with valid relation data.
        """
        if event.app is None:  # pyright: ignore[reportUnnecessaryComparison]
            logger.debug("No remote application yet")
            return
        app_data = event.relation.data[event.app]
        for unit in event.relation.units:
            if not is_requirer_data_valid(app_data, event.relation.data[unit]):
                logger.debug("Invalid data from unit %r", unit.name)
                continue
            self.on.new_vault_kv_client_attached.emit(
                relation=event.relation,
                app_name=event.app.name,
                unit_name=unit.name,
                mount_suffix=event.relation.data[event.app]["mount_suffix"],
                egress_subnets=get_egress_subnets_list_from_relation_data(
                    event.relation.data[unit]
                ),
                nonce=event.relation.data[unit]["nonce"],
            )

    def _on_vault_kv_relation_departed(self, event: ops.RelationDepartedEvent):
        """Handle relation departed."""
        if event.departing_unit:
            self.on.vault_kv_client_detached.emit(unit_name=event.departing_unit.name)

    def remove_unit_credentials(self, relation: ops.Relation, nonce: str | Iterable[str]):
        """Remove nonce(s) from the relation."""
        if not self.charm.unit.is_leader():
            return

        if isinstance(nonce, str):
            nonce = [nonce]

        credentials = self.get_credentials(relation)

        for n in nonce:
            credentials.pop(n, None)

        relation.data[self.charm.app]["credentials"] = json.dumps(credentials, sort_keys=True)

    def get_credentials(self, relation: ops.Relation) -> dict[str, str]:
        """Get the unit credentials from the app relation data and load it as a dict."""
        return json.loads(relation.data[self.charm.app].get("credentials", "{}"))

    def get_kv_requests(self, relation_id: int | None = None) -> list[KVRequest]:
        """Get all KV requests for the relation."""
        kv_requests: list[KVRequest] = []
        relations = (
            [
                relation
                for relation in self.model.relations.get(self.relation_name, [])
                if relation.id == relation_id
            ]
            if relation_id is not None
            else self.model.relations.get(self.relation_name, [])
        )
        for relation in relations:
            assert isinstance(relation.app, ops.Application)
            if not relation.active:
                continue
            app_data = relation.data[relation.app]
            for unit in relation.units:
                unit_data = relation.data[unit]
                if not is_requirer_data_valid(app_data=app_data, unit_data=unit_data):
                    continue
                kv_requests.append(
                    KVRequest(
                        relation=relation,
                        app_name=relation.app.name,
                        unit_name=unit.name,
                        mount_suffix=app_data["mount_suffix"],
                        egress_subnets=get_egress_subnets_list_from_relation_data(unit_data),
                        nonce=unit_data["nonce"],
                    )
                )
        return kv_requests

    def set_kv_data(
        self,
        relation: ops.Relation,
        mount: str,
        ca_certificate: str,
        vault_url: str,
        nonce: str,
        credentials_juju_secret_id: str,
    ):
        """Set the kv data on the relation."""
        if not self.charm.unit.is_leader():
            return
        if not relation.active:
            logger.warning("Relation is not active")
            return
        credentials = self.get_credentials(relation)
        credentials[nonce] = credentials_juju_secret_id
        relation.data[self.charm.app]["credentials"] = json.dumps(credentials, sort_keys=True)
        relation.data[self.charm.app]["vault_url"] = vault_url
        relation.data[self.charm.app]["ca_certificate"] = ca_certificate
        relation.data[self.charm.app]["mount"] = mount


class VaultKvBaseEvent(ops.RelationEvent):
    """Base class for VaultKV requirer events."""

    def __init__(
        self, handle: ops.Handle, relation_id: int, relation_name: str, relation: ops.Relation
    ):
        super().__init__(handle, relation)
        self.relation_id = relation_id
        self.relation_name = relation_name

    def snapshot(self) -> dict[str, Any]:
        """Return snapshot data that should be persisted."""
        return dict(
            super().snapshot(),
            relation_id=self.relation_id,
            relation_name=self.relation_name,
        )

    def restore(self, snapshot: dict[str, Any]):
        """Restore the value state from a given snapshot."""
        super().restore(snapshot)
        self.relation_id = snapshot["relation_id"]
        self.relation_name = snapshot["relation_name"]


class VaultKvConnectedEvent(VaultKvBaseEvent):
    """VaultKvConnectedEvent Event."""

    pass


class VaultKvReadyEvent(VaultKvBaseEvent):
    """VaultKvReadyEvent Event."""

    pass


class VaultKvRequireEvents(ops.ObjectEvents):
    """List of events that the Vault Kv requirer charm can leverage."""

    connected = ops.EventSource(VaultKvConnectedEvent)
    ready = ops.EventSource(VaultKvReadyEvent)
    gone_away = ops.EventSource(VaultKvGoneAwayEvent)


class VaultKvRequires(ops.Object):
    """Class to be instantiated by the requiring side of the relation."""

    on = VaultKvRequireEvents()

    def __init__(
        self,
        charm: ops.CharmBase,
        relation_name: str,
        mount_suffix: str,
    ) -> None:
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name
        self.mount_suffix = mount_suffix
        self.framework.observe(
            self.charm.on[relation_name].relation_joined,
            self._handle_relation,
        )
        self.framework.observe(
            self.charm.on.config_changed,
            self._handle_relation,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed,
            self._on_vault_kv_relation_changed,
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_broken,
            self._on_vault_kv_relation_broken,
        )

    def _handle_relation(self, _: ops.EventBase):
        """Run when a new unit joins the relation or when the address of the unit changes.

        Set the secret backend in the application databag if we are the leader.
        Emit the connected event.
        """
        relations = self.charm.model.relations.get(self.relation_name, [])
        if not relations:
            return

        for relation in relations:
            if self.charm.unit.is_leader():
                relation.data[self.charm.app]["mount_suffix"] = self.mount_suffix
            self.on.connected.emit(
                relation.id,
                relation.name,
                relation,
            )

    def _on_vault_kv_relation_changed(self, event: ops.RelationChangedEvent):
        """Handle relation changed."""
        if event.app is None:  # pyright: ignore[reportUnnecessaryComparison]
            logger.debug("No remote application yet")
            return

        if (
            is_provider_data_valid(event.relation.data[event.app])
            and self.get_unit_credentials(event.relation) is not None
        ):
            self.on.ready.emit(
                event.relation.id,
                event.relation.name,
                event.relation,
            )

    def _on_vault_kv_relation_broken(self, event: ops.RelationBrokenEvent):
        """Handle relation broken."""
        self.on.gone_away.emit()

    def request_credentials(
        self, relation: ops.Relation, egress_subnet: list[str] | str, nonce: str
    ) -> None:
        """Request credentials from the vault-kv relation.

        Credentials are tied to the unit egress_subnet, so if the egress_subnet
        changes a new secret id must be generated.

        A change in egress_subnets can happen when the pod is rescheduled to a different
        node by the underlying substrate without a change from Juju.

        Args:
            relation: The relation object.
            egress_subnet: The egress subnets requesting the credentials for.
            nonce: The nonce that identifies the unit.
        """
        if isinstance(egress_subnet, str):
            egress_subnet = [egress_subnet]
        relation.data[self.charm.unit]["egress_subnet"] = ",".join(egress_subnet)
        relation.data[self.charm.unit]["nonce"] = nonce

    def get_vault_url(self, relation: ops.Relation) -> str | None:
        """Return the vault_url from the relation."""
        return relation.data[relation.app].get("vault_url")

    def get_ca_certificate(self, relation: ops.Relation) -> str | None:
        """Return the ca_certificate from the relation."""
        return relation.data[relation.app].get("ca_certificate")

    def get_mount(self, relation: ops.Relation) -> str | None:
        """Return the mount from the relation."""
        return relation.data[relation.app].get("mount")

    def get_unit_credentials(self, relation: ops.Relation) -> str | None:
        """Return the unit credentials from the relation.

        Unit credentials are stored in the relation data as a Juju secret id.
        """
        nonce = relation.data[self.charm.unit].get("nonce")
        if nonce is None or relation.app is None:  # pyright: ignore[reportUnnecessaryComparison]
            return None
        return json.loads(relation.data[relation.app].get("credentials", "{}")).get(nonce)
