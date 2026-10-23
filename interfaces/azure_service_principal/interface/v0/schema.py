"""This file defines the schemas for the provider and requirer sides of the azure_service_principal interface."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


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

    subscription_id: str | None = Field(
        default=None,
        alias="subscription-id",
        description="The unique identifier for an Azure subscription.",
        examples=["12345678-1234-1234-1234-1234567890ab"],
        title="Subscription ID",
    )

    tenant_id: str | None = Field(
        default=None,
        alias="tenant-id",
        description="The unique identifier of the Azure Active Directory (Entra ID) tenant.",
        examples=["87654321-4321-4321-4321-ba0987654321"],
        title="Tenant ID",
    )

    secret_extra: str | None = Field(
        default=None,
        alias="secret-extra",
        description=(
            "A Juju Secret ID that points to a secret containing client-id (the Application ID"
            " for the service principal) and client-secret (used for authentication)."
        ),
        examples=["secret://91f805c5-5b49-47a3-8e7b-70befa766caf/d40rbhnmp25c76d6bdn0"],
        title="Credentials Secret ID",
    )


class RequirerAppData(ProviderAppData):
    """The requirer's application databag.

    The current library copies the provider's databag here for its own use. Requirers on the
    older data_interfaces v0 based library (such as velero-operator) write requested-secrets and
    provided-secrets instead. The provider reads neither.
    """

    requested_secrets: list[str] | None = Field(
        default=None,
        alias="requested-secrets",
        description="Provider fields the requirer wants delivered as Juju secrets. A JSON array on the wire.",
        examples=[["client-id", "client-secret"]],
        title="Requested secrets",
    )

    provided_secrets: list[str] | None = Field(
        default=None,
        alias="provided-secrets",
        description="Requirer fields the library would deliver as Juju secrets. A JSON array on the wire.",
        examples=[["username", "password", "tls", "tls-ca", "uris"]],
        title="Provided secrets",
    )

    @field_validator("requested_secrets", "provided_secrets", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("requested_secrets", "provided_secrets")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)


class RequirerUnitData(_BareStringDatabag):
    """The requirer's unit databag, written by the older data_interfaces v0 based library for its own use."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    requested_secrets: list[str] | None = Field(
        default=None,
        alias="requested-secrets",
        description="A copy of requested-secrets from the application databag. A JSON array on the wire.",
        examples=[["client-id", "client-secret"]],
        title="Requested secrets",
    )

    provided_secrets: list[str] | None = Field(
        default=None,
        alias="provided-secrets",
        description="A copy of provided-secrets from the application databag. A JSON array on the wire.",
        examples=[["username", "password", "tls", "tls-ca", "uris"]],
        title="Provided secrets",
    )

    data: dict[str, str] | None = Field(
        default=None,
        description=(
            "The provider's application databag as last seen by the requirer, used by the"
            " library to compute diffs. A JSON object on the wire."
        ),
        examples=[{"subscription-id": "12345678-1234-1234-1234-1234567890ab"}],
        title="Last seen provider data",
    )

    @field_validator("requested_secrets", "provided_secrets", "data", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("requested_secrets", "provided_secrets", "data")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)


ProviderUnitData = None
