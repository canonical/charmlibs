"""This file defines the schemas for the provider and requirer sides of the karapace_client interface."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtraUserRole(str, Enum):
    admin = "admin"
    user = "user"


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

    subject: str = Field(
        description="The subject that has been made available to the relation user. Name defined in the Requirer's subject field",
        examples=["subject-1"],
        title="Subject name",
    )

    username: str = Field(
        description="Username for connecting to the Karapace service",
        examples=["relation-14"],
        title="Karapace username",
    )

    password: str = Field(
        description="Password for connecting to the Karapace service",
        examples=["alphanum-32byte-random"],
        title="Karapace password",
    )

    endpoints: str = Field(
        description="A list of endpoints used to connect to the subject, comma separated on the wire",
        examples=["10.141.78.155:8082,10.141.78.62:8082,10.141.78.186:8082"],
        title="Karapace server endpoints",
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

    subject: str = Field(
        description="The subject name access requested by the requirer",
        examples=["subject-1"],
        title="Subject name",
    )

    extra_user_roles: str | None = Field(
        default="admin",
        alias="extra-user-roles",
        description="Any extra user roles requested by the requirer",
        examples=["admin", "user"],
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
        description="List of permissions to assign to the custom entity, in JSON format. Written to the databag as an opaque string",
        examples=[
            "[{\"resource_name\": \"schemas\", \"resource_type\": \"SUBJECT\", \"privileges\": [\"READ\"]}]"
        ],
        title="Entity permissions",
    )

    @field_validator("extra_user_roles", mode="before")
    @classmethod
    def extra_user_roles_validator(cls, value: str | None) -> str | None:
        if value is None:
            return value

        try:
            _role = ExtraUserRole(value)
        except ValueError:
            raise ValueError(f"Role {value} is not valid.")

        return value


ProviderUnitData = None
RequirerUnitData = None
