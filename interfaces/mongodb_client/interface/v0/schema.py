"""This file defines the schemas for the provider and requirer sides of the mongodb_client interface."""

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
        description="Username for connecting to the requested database",
        examples=["relation-14"],
        title="Database user name",
    )

    password: str = Field(
        description="Password for connecting to the requested database",
        examples=["alphanum-32byte-random"],
        title="Database user password",
    )

    endpoints: str = Field(
        description="A list of database endpoints used to connect to the database",
        examples=["unit-1:port,unit-2:port"],
        title="Database endpoints",
    )

    uris: str | None = Field(
        None,
        description="A list of connection strings in URI format used to connect to the database",
        examples=["mongodb://user:pass@host1:port,host2:port/authDBname?replset=rs0"],
        title="Database URIs",
    )

    replset: str | None = Field(
        None,
        description="The name of the replication set",
        examples=["rs0"],
        title="ReplSet",
    )

    version: str | None = Field(
        None,
        description="The version of the database engine",
        examples=["8.0.27-18"],
        title="Version",
    )

    entity_name: str | None = Field(
        None,
        alias="entity-name",
        description="Name for the requested custom entity",
        examples=["custom-role"],
        title="Entity name",
    )

    entity_password: str | None = Field(
        None,
        alias="entity-password",
        description="Password for the requested custom entity",
        examples=["alphanum-32byte-random"],
        title="Entity password",
    )


class RequirerAppData(_BareStringDatabag):
    """The databag for the requirer side of this interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    database: str = Field(
        description="The database name requested by the requirer",
        examples=["myapp"],
        title="Database name",
    )

    requested_secrets: list[str] = Field(
        alias="requested-secrets",
        description="Any provider field which should be transferred as Juju Secret. A JSON array on the wire.",
        examples=[["username", "password"]],
        title="Requested secrets",
    )

    extra_user_roles: str | None = Field(
        None,
        alias="extra-user-roles",
        description="Any extra user roles requested by the requirer",
        examples=["default,admin"],
        title="Extra user roles",
    )

    extra_group_roles: str | None = Field(
        None,
        alias="extra-group-roles",
        description="Any extra group roles requested by the requirer",
        examples=["charmed_read"],
        title="Extra group roles",
    )

    entity_type: str | None = Field(
        None,
        alias="entity-type",
        description="Type of the requested entity (user / group)",
        examples=["USER", "GROUP"],
        title="Entity type",
    )

    entity_permissions: str | None = Field(
        None,
        alias="entity-permissions",
        description="List of permissions to assign to the custom entity, in JSON format",
        examples=[
            "[{\"resource_name\": \"posts\", \"resource_type\": \"COLLECTION\", \"privileges\": [\"READ\"]}]"
        ],
        title="Entity permissions",
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
