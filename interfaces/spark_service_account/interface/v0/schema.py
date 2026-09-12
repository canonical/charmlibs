"""This file defines the schemas for the provider and requirer sides of this relation interface."""

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
    """The provider's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    service_account: str = Field(
        alias="service-account",
        description="The name of the service account to be created and the namespace in"
        " which the service account is to be created.",
        examples=["test_namespace:test_service_account"],
        title="Service Account",
    )

    secret_extra: str = Field(
        alias="secret-extra",
        description="The name of the Spark properties and K8s resource manifest secret "
        "to use. The secret contains 1. `spark-properties`, the list of different Spark"
        " properties that are associated with this service account and 2. "
        "`resource-manifest`, which contains the YAML dump of the K8s service account.",
        examples=["secret://59060ecc-0495-4a80-8006-5f1fc13fd783/cjqub7fubg2s77p3niog"],
        title="Spark properties and K8s resource manifest secret",
    )


class RequirerAppData(_BareStringDatabag):
    """The requirer's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    service_account: str = Field(
        alias="service-account",
        description="The name of the service account to be created and the namespace in"
        " which the service account is to be created.",
        examples=["test_namespace:test_service_account"],
        title="Service Account",
    )

    requested_secrets: list[str] = Field(
        alias="requested-secrets",
        description="Any provider field which should be transfered as Juju Secret. This"
        " field is auto-populated by the data-interfaces lib.",
        examples=[["spark-properties", "resource-manifest"]],
        title="Requested secrets",
    )

    skip_creation: str = Field(
        alias="skip-creation",
        description="Define whether the providing charm should skip the creation of the"
        " service account requested.",
        examples=["false", "true"],
        title="Skip creation",
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
