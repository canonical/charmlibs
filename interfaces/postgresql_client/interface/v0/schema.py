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

    database: str = Field(
        description="The database name delivered by the provider. Might not be the same as requested by the requirer",
        examples=["myapp"],
        title="Database name",
    )

    username: str = Field(
        description="Username for connecting to the requested database. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["relation-14"],
        title="Database user name",
    )

    password: str = Field(
        description="Password for connecting to the requested database. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["alphanum-32byte-random"],
        title="Database user password",
    )

    endpoints: str = Field(
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

    version: str | None = Field(
        None,
        description="The version of the database engine. A bare string on the wire",
        examples=["16.8.1"],
        title="Version",
    )

    subordinated: str | None = Field(
        "true",
        description="Indicates that the provider should check the unit state when scaling up. A bare string on the wire, only ever written as the literal \"true\"",
        examples=["true"],
        title="Subordinated",
    )

    state: str | None = Field(
        "ready",
        description="Unit level data to indicate that a subordinate unit is ready to serve. A bare string on the wire. Note that the library reads this from the provider's *unit* databag, not the application databag",
        examples=["ready"],
        title="State",
    )

    tls: str | None = Field(
        None,
        description="Flag that indicates whether TLS is being used by the PostgreSQL charm or not. A bare string on the wire, not a JSON boolean; the library writes the literal \"True\" alongside tls-ca. May be delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["true", "false"],
        title="TLS",
    )

    tls_ca: str | None = Field(
        None,
        alias="tls-ca",
        description="The TLS CA chain of certificates, if TLS is set. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["-----BEGIN CERTIFICATE-----\nexample\n-----END CERTIFICATE-----"],
        title="TLS CA",
    )

    entity_name: str | None = Field(
        None,
        alias="entity-name",
        description="Name for the requested custom entity. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["custom-role"],
        title="Entity name",
    )

    entity_password: str | None = Field(
        None,
        alias="entity-password",
        description="Password for the requested custom entity. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["alphanum-32byte-random"],
        title="Entity password",
    )

    prefix_databases: str | None = Field(
        None,
        alias="prefix-databases",
        description="Comma separated list of databases matching a requested prefix. A bare string on the wire; the library sorts the names before joining them, and writes an empty string (which Juju erases) when no database matches",
        examples=["database1,database2"],
        title="Prefix databases",
    )


class RequirerAppData(_BareStringDatabag):
    """The databag for the requirer side of this interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    database: str = Field(
        description="The database name requested by the requirer. A bare string on the wire",
        examples=["myapp"],
        title="Database name",
    )

    requested_secrets: list[str] = Field(
        alias="requested-secrets",
        description="Any provider field which should be transferred as Juju Secret. A JSON array on the wire",
        examples=[["username", "password"]],
        title="Requested secrets",
    )

    external_node_connectivity: str | None = Field(
        "true",
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

    @field_validator("requested_secrets", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("requested_secrets")
    def _dump_json(self, value: object) -> str:
        return json.dumps(value)


ProviderUnitData = None
RequirerUnitData = None
