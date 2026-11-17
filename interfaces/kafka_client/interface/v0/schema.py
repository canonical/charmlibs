"""This file defines the schemas for the provider and requirer sides of the kafka_client interface."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtraUserRole(str, Enum):
    admin = "admin"
    consumer = "consumer"
    producer = "producer"


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

    topic: str = Field(
        description="The topic that has been made available to the relation user. Name defined in the Requirer's topic field. A bare string on the wire",
        examples=["topic-1", "appname-*"],
        title="Topic name",
    )

    username: str = Field(
        description="Username for connecting to the Kafka cluster. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["relation-14"],
        title="Kafka SASL/SCRAM username",
    )

    password: str = Field(
        description="Password for connecting to the Kafka cluster. A bare string on the wire, but usually delivered in a Juju secret instead, in which case the key is absent from the databag",
        examples=["alphanum-32byte-random"],
        title="Kafka SASL/SCRAM password",
    )

    endpoints: str = Field(
        description="A list of endpoints used to connect to the topic. A bare string on the wire, comma separated if there is more than one endpoint",
        examples=["10.141.78.155:9092,10.141.78.62:9092,10.141.78.186:9092"],
        title="Kafka server endpoints",
    )

    consumer_group_prefix: str | None = Field(
        None,
        alias="consumer-group-prefix",
        description="A prefix for wildcard consumer-group IDs that have been granted permissions. A bare string on the wire",
        examples=["relation-14-"],
        title="Kafka consumer group prefix",
    )

    zookeeper_uris: str | None = Field(
        None,
        alias="zookeeper-uris",
        description="A comma-seperated list of Zookeeper server URIs, and Kafka cluster zNode. A bare string on the wire",
        examples=["10.141.78.155:2181,10.141.78.62:2181,10.141.78.186:2181/kafka"],
        title="Zookeeper URIs",
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


class RequirerAppData(_BareStringDatabag):
    """The databag for the requirer side of this interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    topic: str = Field(
        description="The topic name access requested by the requirer. A bare string on the wire",
        examples=["topic-1", "appname-*"],
        title="Topic name",
    )

    consumer_group_prefix: str | None = Field(
        None,
        alias="consumer-group-prefix",
        description="A prefix for wildcard consumer-group IDs that have been granted permissions. A bare string on the wire",
        examples=["relation-14-"],
        title="Kafka consumer group prefix",
    )

    extra_user_roles: str | None = Field(
        None,
        alias="extra-user-roles",
        description="Any extra user roles requested by the requirer. A bare string on the wire, comma separated if there is more than one role",
        examples=[
            "consumer",
            "producer",
            "admin",
            "consumer,producer",
            "consumer,admin",
            "producer,admin",
            "consumer,producer,admin",
        ],
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
            "[{\"resource_name\": \"messages\", \"resource_type\": \"TOPIC\", \"privileges\": [\"READ\"]}]"
        ],
        title="Entity permissions",
    )

    @field_validator("extra_user_roles", mode="before")
    @classmethod
    def capitalize(cls, value: str) -> str:
        extra_roles = value.split(",")

        for role in extra_roles:
            if role not in ExtraUserRole:
                raise ValueError(f"Role {role} is not valid.")

        return value


ProviderUnitData = None
RequirerUnitData = None
