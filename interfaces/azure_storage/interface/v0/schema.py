"""This file defines the schemas for the provider and requirer sides of the azure_storage interface."""

import json
import pathlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer, field_validator


class ConnectionProtocolEnum(str, Enum):
    blob_storage_insecure = "wasb"
    blob_storage_secure = "wasbs"
    adls_gen2_insecure = "abfs"
    adls_gen2_secure = "abfss"


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

    container: str = Field(
        description="The name of the Azure storage container provided by the provider.",
        examples=["mycontainer"],
        title="Container",
    )

    storage_account: str = Field(
        alias="storage-account",
        description="The name of Azure storage account.",
        examples=["test-storage-account"],
        title="Storage account",
    )

    connection_protocol: ConnectionProtocolEnum = Field(
        alias="connection-protocol",
        description="The connection protocol to be used to connect to Azure Storage.",
        examples=["wasb", "wasbs", "abfs", "abfss"],
        default=ConnectionProtocolEnum.adls_gen2_secure,
        strict=False,
        title="Connection protocol",
    )

    secret_key: SecretStr = Field(
        alias="secret-key",
        description="Secret key corresponding to the storage account for connecting to the object storage.",
        examples=["random-secret-key"],
        title="Secret key",
    )

    path: str = Field(
        description="The path inside the container to store objects.",
        examples=["foo/bar"],
        title="Path",
    )

    endpoint: str = Field(
        description="The endpoint corresponding to the specific container and storage account.",
        examples=["abfss://test-container@test-account.dfs.core.windows.net/"],
        title="Endpoint URL",
    )

    @field_serializer("connection_protocol")
    def _dump_enum(self, value: ConnectionProtocolEnum) -> str:
        """Write the enum's wire string rather than the enum member."""
        return value.value

    @field_serializer("secret_key")
    def _reveal(self, value: SecretStr) -> str:
        """Write the real secret to the databag rather than the masked repr."""
        return value.get_secret_value()

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: str) -> str:
        """Check the value is a usable path, keeping any trailing slash."""
        pathlib.PurePosixPath(value)  # raises if it isn't a usable path
        return value


class RequirerAppData(_BareStringDatabag):
    """The requirer's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    container: str = Field(
        description="The name of the container that's requested by the requirer.",
        examples=["mycontainer"],
        title="container",
    )

    requested_secrets: list[str] = Field(
        alias="requested-secrets",
        description="Any provider field which should be transfered as Juju Secret. A JSON array on the wire.",
        examples=[["username", "password", "tls-ca", "uris"]],
        title="Requested secrets",
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


ProviderUnitData = None
RequirerUnitData = None
