"""This file defines the schemas for the provider and requirer sides of the postgresql_client interface."""

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
    """The databag for the provider side of this interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    database: str | None = Field(
        None,
        description="The database name delivered by the provider. Might not be the same as requested by the requirer",
        examples=["myapp"],
        title="Database name",
    )

    username: str | None = Field(
        None,
        description="Username for connecting to the requested database. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["relation-14"],
        title="Database user name",
    )

    password: str | None = Field(
        None,
        description="Password for connecting to the requested database. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["alphanum-32byte-random"],
        title="Database user password",
    )

    endpoints: str | None = Field(
        None,
        description="A list of database endpoints used to connect to the database. A bare string on the wire, comma separated if there is more than one endpoint",
        examples=["unit-1:port,unit-2:port"],
        title="Database endpoints",
    )

    uris: str | None = Field(
        None,
        description="A list of connection strings in URI format used to connect to the database. A bare string on the wire, but may be delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["postgresql://user:pass@host-1:port,host-2:port/mydb"],
        title="Database URIs",
    )

    read_only_endpoints: str | None = Field(
        None,
        alias="read-only-endpoints",
        description="A list of endpoints used to connect to the database in read-only mode. A bare string on the wire, comma separated if there is more than one endpoint",
        examples=["unit-1:port,unit-2:port"],
        title="Database read-only endpoints",
    )

    read_only_uris: str | None = Field(
        None,
        alias="read-only-uris",
        description="A list of connection strings in URI format used to connect to the read only endpoint of the database. A bare string on the wire, but may be delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["postgresql://user:pass@host-1:port,host-2:port/mydb"],
        title="Database read-only URIs",
    )

    secret_user: str | None = Field(
        None,
        alias="secret-user",
        description="URI of the Juju secret holding whichever of username, password, uris and read-only-uris the requirer listed in requested-secrets. A bare string on the wire",
        examples=["secret:cjqub6vubg2s77p3nio0"],
        title="User secret",
    )

    version: str | None = Field(
        None,
        description="The version of the database engine. A bare string on the wire",
        examples=["16.8.1"],
        title="Version",
    )

    subordinated: str | None = Field(
        None,
        description="Indicates that the provider should check the unit state when scaling up. A bare string on the wire, only ever written as the literal \"true\"",
        examples=["true"],
        title="Subordinated",
    )

    tls: str | None = Field(
        None,
        description="Flag that indicates whether TLS is being used by the PostgreSQL charm or not. A bare string on the wire, not a JSON boolean: providers write the literal \"True\" or \"False\". Usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["True", "False"],
        title="TLS",
    )

    tls_ca: str | None = Field(
        None,
        alias="tls-ca",
        description="The TLS CA chain of certificates, if TLS is set; providers write an empty string (which Juju erases) when TLS is off. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["-----BEGIN CERTIFICATE-----\nexample\n-----END CERTIFICATE-----"],
        title="TLS CA",
    )

    secret_tls: str | None = Field(
        None,
        alias="secret-tls",
        description="URI of the Juju secret holding whichever of tls and tls-ca the requirer listed in requested-secrets. A bare string on the wire",
        examples=["secret:cjqub7fubg2s77p3niog"],
        title="TLS secret",
    )

    prefix_databases: str | None = Field(
        None,
        alias="prefix-databases",
        description="Comma separated list of databases matching a requested prefix. A bare string on the wire; the library sorts the names before joining them, and writes an empty string (which Juju erases) when no database matches",
        examples=["database1,database2"],
        title="Prefix databases",
    )

    data: dict[str, str] | None = Field(
        None,
        description="The requirer's application databag as last seen by the provider, used by the library to compute diffs; the requirer library also reads it to check whether entity-type was requested. A JSON object on the wire",
        examples=[{"database": "myapp", "requested-secrets": '["username", "password"]'}],
        title="Last seen requirer data",
    )

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


class ProviderUnitData(_BareStringDatabag):
    """The databag for each unit on the provider side of this interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    state: str | None = Field(
        None,
        description="Set to \"ready\" by a subordinate provider's units once they can serve; requirers wait for it when subordinated is \"true\". A bare string on the wire",
        examples=["ready"],
        title="State",
    )


class RequirerAppData(_BareStringDatabag):
    """The databag for the requirer side of this interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    database: str | None = Field(
        None,
        description="The database name requested by the requirer. A bare string on the wire",
        examples=["myapp"],
        title="Database name",
    )

    requested_secrets: list[str] | None = Field(
        None,
        alias="requested-secrets",
        description="Any provider field which should be transferred as Juju Secret. A JSON array on the wire",
        examples=[
            [
                "username",
                "password",
                "tls",
                "tls-ca",
                "uris",
                "read-only-uris",
                "entity-name",
                "entity-password",
            ]
        ],
        title="Requested secrets",
    )

    provided_secrets: list[str] | None = Field(
        None,
        alias="provided-secrets",
        description="Fields the requirer may itself share as Juju Secrets. A JSON array on the wire",
        examples=[["mtls-cert"]],
        title="Provided secrets",
    )

    external_node_connectivity: str | None = Field(
        None,
        alias="external-node-connectivity",
        description="Provide external connectivity, if subordinate router. A bare string on the wire, only ever written as the literal \"true\"",
        examples=["true"],
        title="External node connectivity",
    )

    extra_user_roles: str | None = Field(
        None,
        alias="extra-user-roles",
        description="Any extra user roles requested by the requirer. A bare string on the wire, comma separated if there is more than one role",
        examples=["default,admin"],
        title="Extra user roles",
    )

    extra_group_roles: str | None = Field(
        None,
        alias="extra-group-roles",
        description="Any extra group roles requested by the requirer. A bare string on the wire, comma separated if there is more than one role",
        examples=["charmed_read"],
        title="Extra group roles",
    )

    entity_type: str | None = Field(
        None,
        alias="entity-type",
        description="Type of the requested entity (user / group). A bare string on the wire",
        examples=["USER", "GROUP"],
        title="Entity type",
    )

    entity_permissions: str | None = Field(
        None,
        alias="entity-permissions",
        description="List of permissions to assign to the custom entity, in JSON format. The library treats this as an opaque string, so it is written to the databag as-is rather than being re-encoded",
        examples=[
            "[{\"resource_name\": \"items\", \"resource_type\": \"TABLE\", \"privileges\": [\"SELECT\"]}]"
        ],
        title="Entity permissions",
    )

    requested_entity_secret: str | None = Field(
        None,
        alias="requested-entity-secret",
        description="URI of a Juju secret containing a definition of the credentials to be created by the provider. A bare string on the wire",
        examples=["secret:d2fjn1fmp25004or68b0"],
        title="Requested entity secret",
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
    """The requirer's unit databag, written by the library for its own bookkeeping."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    requested_secrets: list[str] | None = Field(
        None,
        alias="requested-secrets",
        description="A copy of requested-secrets from the application databag. A JSON array on the wire",
        examples=[
            [
                "username",
                "password",
                "tls",
                "tls-ca",
                "uris",
                "read-only-uris",
                "entity-name",
                "entity-password",
            ]
        ],
        title="Requested secrets",
    )

    provided_secrets: list[str] | None = Field(
        None,
        alias="provided-secrets",
        description="A copy of provided-secrets from the application databag. A JSON array on the wire",
        examples=[["mtls-cert"]],
        title="Provided secrets",
    )

    data: dict[str, str] | None = Field(
        None,
        description="The provider's application databag as last seen by the requirer, used by the library to compute diffs. A JSON object on the wire",
        examples=[
            {
                "database": "myapp",
                "endpoints": "10.0.0.1:5432",
                "secret-user": "secret:cjqub6vubg2s77p3nio0",
            }
        ],
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
