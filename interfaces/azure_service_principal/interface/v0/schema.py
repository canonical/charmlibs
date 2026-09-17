"""This file defines the schemas for the provider and requirer sides of the azure_service_principal interface."""

import json
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
    """Credentials for an Azure Service Principal."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    subscription_id: str = Field(
        alias="subscription-id",
        description="The unique identifier for an Azure subscription.",
        examples=["12345678-1234-1234-1234-1234567890ab"],
        title="Subscription ID",
    )

    tenant_id: str = Field(
        alias="tenant-id",
        description="The unique identifier of the Azure Active Directory (Entra ID) tenant.",
        examples=["87654321-4321-4321-4321-ba0987654321"],
        title="Tenant ID",
    )

    client_id: str = Field(
        alias="client-id",
        description="The Application (client) ID for the service principal.",
        examples=["a1b2c3d4-e5f6-a7b8-c9d0-e1f2a3b4c5d6"],
        title="Client ID",
    )

    client_secret: SecretStr = Field(
        alias="client-secret",
        description="The client secret for the service principal, used for authentication.",
        examples=["aBcDeFgHiJkLmNoPqRsTuVwXyZ123456-~7890_"],
        title="Client Secret",
    )

    @field_serializer("client_secret")
    def _reveal(self, value: SecretStr) -> str:
        """Write the real secret to the databag rather than the masked repr."""
        return value.get_secret_value()


class RequirerAppData(_BareStringDatabag):
    """The fields the requirer asks to be delivered as Juju secrets."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    requested_secrets: list[str] = Field(
        alias="requested-secrets",
        description="Any provider field which should be transfered as a Juju secret. A JSON array on the wire.",
        examples=[["client-id", "client-secret"]],
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
