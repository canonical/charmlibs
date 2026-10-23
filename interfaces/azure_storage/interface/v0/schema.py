"""This file defines the schemas for the provider and requirer sides of the azure_storage interface."""

import json
import pathlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer, field_validator


class _BareStringDatabag(BaseModel):
    """Base class for databag models that don't strictly JSON encode all entries."""

    @staticmethod
    def __juju_decoder__(value: str) -> str:
        """Pass Juju's string through unmodified to be decoded by individual field validators."""
        return value

    @staticmethod
    def __juju_encoder__(value: str | None) -> str:
        """Convert `None` to "", erasing the value; Ops will error on a non-string."""
        return "" if value is None else value


class ProviderAppData(_BareStringDatabag):
    """The provider's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    container: str | None = Field(
        default=None,
        description="The name of the Azure storage container provided by the provider.",
        examples=["mycontainer"],
        title="Container",
    )

    storage_account: str | None = Field(
        default=None,
        alias="storage-account",
        description="The name of Azure storage account.",
        examples=["test-storage-account"],
        title="Storage account",
    )

    connection_protocol: str | None = Field(
        default=None,
        alias="connection-protocol",
        description=(
            "The connection protocol to be used to connect to Azure Storage: wasb or wasbs for"
            " Azure Blob Storage, abfs or abfss for Azure Data Lake Storage Gen2, or http or"
            " https for the REST API. The provider passes its configuration through unchecked."
        ),
        examples=["abfss", "wasbs", "https"],
        title="Connection protocol",
    )

    secret_extra: str | None = Field(
        default=None,
        alias="secret-extra",
        description=(
            "A Juju Secret ID that points to a secret containing secret-key, the key"
            " corresponding to the storage account for connecting to the object storage."
        ),
        examples=["secret://91f805c5-5b49-47a3-8e7b-70befa766caf/d40rbhnmp25c76d6bdn0"],
        title="Credentials Secret ID",
    )

    secret_key: SecretStr | None = Field(
        default=None,
        alias="secret-key",
        description=(
            "The storage account key in plain text, written instead of secret-extra when the"
            " requirer didn't list it in requested-secrets or Juju secrets are unavailable."
        ),
        examples=["random-secret-key"],
        title="Secret key",
    )

    path: str | None = Field(
        default=None,
        description="The path inside the container to store objects.",
        examples=["foo/bar"],
        title="Path",
    )

    endpoint: str | None = Field(
        default=None,
        description="The endpoint corresponding to the specific container and storage account.",
        examples=["abfss://test-container@test-account.dfs.core.windows.net/"],
        title="Endpoint URL",
    )

    resource_group: str | None = Field(
        default=None,
        alias="resource-group",
        description="The name of the Azure resource group where the storage account is located.",
        examples=["my-resource-group"],
        title="Resource group",
    )

    version: str | None = Field(
        default=None,
        description="The schema version the provider is using. Absent for the oldest providers.",
        examples=["1"],
        title="Schema version",
    )

    data: dict[str, str] | None = Field(
        default=None,
        description=(
            "The requirer's application databag as last seen by the provider, used by the"
            " library to compute diffs. A JSON object on the wire."
        ),
        examples=[{"container": "mycontainer", "requested-secrets": '["secret-key"]'}],
        title="Last seen requirer data",
    )

    @field_serializer("secret_key")
    def _reveal(self, value: SecretStr | None) -> str | None:
        """Write the real secret to the databag rather than the masked repr."""
        return None if value is None else value.get_secret_value()

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: str | None) -> str | None:
        """Check the value is a usable path, keeping any trailing slash."""
        if value is not None:
            pathlib.PurePosixPath(value)  # raises if it isn't a usable path
        return value

    @field_validator("data", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("data")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)


class RequirerAppData(_BareStringDatabag):
    """The requirer's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    container: str | None = Field(
        default=None,
        description=(
            "The name of the container that's requested by the requirer, or the placeholder"
            " relation-<id> written to signal an older provider."
        ),
        examples=["mycontainer", "relation-3"],
        title="container",
    )

    requested_secrets: list[str] | None = Field(
        default=None,
        alias="requested-secrets",
        description="Any provider field which should be transfered as Juju Secret. A JSON array on the wire.",
        examples=[["secret-key"]],
        title="Requested secrets",
    )

    version: str | None = Field(
        default=None,
        description="The schema version the requirer is using. Absent for the oldest requirers.",
        examples=["1"],
        title="Schema version",
    )

    @field_validator("requested_secrets", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("requested_secrets")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)


class RequirerUnitData(_BareStringDatabag):
    """The requirer's unit databag, written by the library for its own bookkeeping."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    requested_secrets: list[str] | None = Field(
        default=None,
        alias="requested-secrets",
        description="A copy of requested-secrets from the application databag. A JSON array on the wire.",
        examples=[["secret-key"]],
        title="Requested secrets",
    )

    data: dict[str, str] | None = Field(
        default=None,
        description=(
            "The provider's application databag as last seen by the requirer, used by the"
            " library to compute diffs. A JSON object on the wire."
        ),
        examples=[{"container": "mycontainer", "storage-account": "test-storage-account"}],
        title="Last seen provider data",
    )

    @field_validator("requested_secrets", "data", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("requested_secrets", "data")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)


ProviderUnitData = None
