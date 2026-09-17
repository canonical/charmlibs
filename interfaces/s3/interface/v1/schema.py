"""Schemas for v1 of the s3 interface."""

import json
from enum import Enum, IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class S3URIStyleEnum(str, Enum):
    path = "path"
    host = "host"


class S3APIVersion(IntEnum):
    v2 = 2
    v4 = 4


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
    """Data expected on the provider side for the s3 v1 interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    bucket: str | None = Field(
        description="The bucket/container name delivered by the provider.",
        examples=["minio"],
        title="Bucket name",
    )

    lib_version: str = Field(
        alias="lib-version",
        description="The S3 lib version used by the provider charm.",
        examples=["1.10"],
        title="S3 lib version",
    )

    secret_extra: str = Field(
        alias="secret-extra",
        description=(
            "A Juju Secret ID that points to a secret containing access-key and"
            " secret-key for connecting to the object storage."
        ),
        examples=["secret://91f805c5-5b49-47a3-8e7b-70befa766caf/d40rbhnmp25c76d6bdn0"],
        title="Credentials Secret ID",
    )

    path: str | None = Field(
        description="The path inside the bucket/container to store objects.",
        examples=["my/path/"],
        title="Path",
    )

    endpoint: str | None = Field(
        description="The endpoint used to connect to the object storage.",
        examples=["https://minio-endpoint/"],
        title="Endpoint URL",
    )

    region: str | None = Field(
        description="The region used to connect to the object storage.",
        examples=["us-east-1"],
        title="Region",
    )

    s3_uri_style: S3URIStyleEnum | None = Field(
        alias="s3-uri-style",
        description="The S3 protocol specific bucket path lookup type.",
        examples=["path", "host"],
        strict=False,
        title="S3 URI Style",
    )

    storage_class: str | None = Field(
        alias="storage-class",
        description="Storage Class for objects uploaded to the object storage.",
        examples=["glacier"],
        title="Storage Class",
    )

    tls_ca_chain: list[str] | None = Field(
        alias="tls-ca-chain",
        description=(
            "The complete CA chain, which can be used for HTTPS validation."
            " A JSON array on the wire."
        ),
        examples=[["base64-encoded-ca-chain=="]],
        title="TLS CA Chain",
    )

    s3_api_version: S3APIVersion | None = Field(
        alias="s3-api-version",
        description="S3 protocol specific API signature. A decimal string on the wire.",
        examples=[2, 4],
        strict=False,
        title="S3 API signature",
    )

    attributes: list[str] | None = Field(
        description="The custom metadata (HTTP headers). Semicolon separated on the wire.",
        examples=[
            [
                "Cache-Control=max-age=90000,min-fresh=9000",
                "X-Amz-Server-Side-Encryption-Customer-Key=CuStoMerKey=",
            ]
        ],
        title="Custom metadata",
    )

    @field_serializer("s3_uri_style")
    def _dump_uri_style(self, value: S3URIStyleEnum | None) -> str | None:
        """Write the enum's wire string rather than the enum member."""
        return None if value is None else value.value

    @field_serializer("s3_api_version")
    def _dump_api_version(self, value: S3APIVersion | None) -> str | None:
        """Write the signature as a decimal string; Ops will error on a non-string."""
        return None if value is None else str(value.value)

    @field_validator("tls_ca_chain", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("tls_ca_chain")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    @field_validator("attributes", mode="before")
    @classmethod
    def _split_semicolon_separated(cls, value: str | list[str] | None) -> list[str] | None:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return value.split(";")

    @field_serializer("attributes")
    def _join_semicolon_separated(self, value: list[str] | None) -> str | None:
        if value is None:
            return None
        return ";".join(value)


class RequirerAppData(_BareStringDatabag):
    """Data expected on the requirer side for the s3 v1 interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    bucket: str | None = Field(
        description="The name of the bucket/container requested by the requirer.",
        examples=["minio"],
        title="Bucket",
    )

    lib_version: str = Field(
        alias="lib-version",
        description="The desired S3 lib version the requirer expects.",
        examples=["1.10"],
        title="S3 lib version",
    )

    path: str | None = Field(
        description="The path inside the bucket/container to store objects.",
        examples=["my/path/"],
        title="Path",
    )

    requested_secrets: str = Field(
        alias="requested-secrets",
        description=(
            "Any provider field which should be transferred as a Juju Secret."
            " A JSON array on the wire, written to the databag as an opaque string."
        ),
        examples=[["access-key", "secret-key"]],
        title="Requested secrets",
    )


ProviderUnitData = None
RequirerUnitData = None
