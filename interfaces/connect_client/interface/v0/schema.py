"""This file defines the schemas for the provider and requirer sides  of `connect_client` charm relation interface."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

PLUGIN_URL_NOT_REQUIRED = "NOT-REQUIRED"


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

    endpoints: str = Field(
        description="A comma-separated list of Kafka Connect REST endpoint(s), including the protocol (either `http` or `https`)",
        examples=["http://10.1.1.100:8083,http://10.1.1.101:8083,http://10.1.1.102:8083"],
        title="Kafka Connect Endpoints",
    )
    secret_user: str = Field(
        alias="secret-user",
        description="The credentials to connect to Kafka Connect. The secret contains [username,password].",
        examples=["secret://59060ecc-0495-4a80-8006-5f1fc13fd783/cjqub6vubg2s77p3nio0"],
        title="Credentials Secret Name",
    )
    secret_tls: str | None = Field(
        None,
        alias="secret-tls",
        description="The name of the TLS secret to use. Leaving this empty will configure a client with TLS disabled. The secret contains [tls,tls-ca].",
        examples=["secret://59060ecc-0495-4a80-8006-5f1fc13fd783/cjqub7fubg2s77p3niog"],
        title="TLS Secret Name",
    )


class RequirerAppData(_BareStringDatabag):
    """The requirer's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    plugin_url: str = Field(
        description=f'URL at which the plugins required by this client are served as a single Tarball. If not required, the requirer should place the sentinel value "{PLUGIN_URL_NOT_REQUIRED}"',
        alias="plugin-url",
        examples=["http://10.1.1.200:8080/route/to/plugins", PLUGIN_URL_NOT_REQUIRED],
        title="Plugin URL",
    )
    requested_secrets: list[str] = Field(
        alias="requested-secrets",
        description="Any provider field which should be transfered as Juju Secret. A JSON array on the wire.",
        examples=[["username", "password", "tls-ca"]],
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
