"""Schemas for v1 of the s3 interface."""

import json
from enum import Enum, IntEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer, field_validator


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
        default=None,
        description="The bucket/container name delivered by the provider.",
        examples=["minio"],
        title="Bucket name",
    )

    version: str | None = Field(
        default=None,
        description=(
            "The schema version the provider is using. Absent for providers that predate it,"
            " which write lib-version or nothing instead."
        ),
        examples=["1"],
        title="Schema version",
    )

    lib_version: str | None = Field(
        default=None,
        alias="lib-version",
        description="The S3 lib version used by the provider charm. Superseded by version.",
        examples=["1.0"],
        title="S3 lib version",
    )

    secret_extra: str | None = Field(
        default=None,
        alias="secret-extra",
        description=(
            "A Juju Secret ID that points to a secret containing access-key and"
            " secret-key for connecting to the object storage."
        ),
        examples=["secret://91f805c5-5b49-47a3-8e7b-70befa766caf/d40rbhnmp25c76d6bdn0"],
        title="Credentials Secret ID",
    )

    access_key: str | None = Field(
        default=None,
        alias="access-key",
        description=(
            "The access key in plain text, written instead of secret-extra when the requirer"
            " didn't list it in requested-secrets or Juju secrets are unavailable."
        ),
        examples=["my-s3-access-key"],
        title="Access key",
    )

    secret_key: SecretStr | None = Field(
        default=None,
        alias="secret-key",
        description=(
            "The secret key in plain text, written instead of secret-extra when the requirer"
            " didn't list it in requested-secrets or Juju secrets are unavailable."
        ),
        examples=["my-s3-secret-key"],
        title="Secret key",
    )

    path: str | None = Field(
        default=None,
        description="The path inside the bucket/container to store objects.",
        examples=["my/path/"],
        title="Path",
    )

    endpoint: str | None = Field(
        default=None,
        description="The endpoint used to connect to the object storage.",
        examples=["https://minio-endpoint/"],
        title="Endpoint URL",
    )

    region: str | None = Field(
        default=None,
        description="The region used to connect to the object storage.",
        examples=["us-east-1"],
        title="Region",
    )

    s3_uri_style: S3URIStyleEnum | None = Field(
        default=None,
        alias="s3-uri-style",
        description="The S3 protocol specific bucket path lookup type.",
        examples=["path", "host"],
        strict=False,
        title="S3 URI Style",
    )

    storage_class: str | None = Field(
        default=None,
        alias="storage-class",
        description="Storage Class for objects uploaded to the object storage.",
        examples=["glacier"],
        title="Storage Class",
    )

    tls_ca_chain: list[str] | None = Field(
        default=None,
        alias="tls-ca-chain",
        description=(
            "The complete CA chain, which can be used for HTTPS validation."
            " A JSON array on the wire."
        ),
        examples=[["base64-encoded-ca-chain=="]],
        title="TLS CA Chain",
    )

    s3_api_version: S3APIVersion | None = Field(
        default=None,
        alias="s3-api-version",
        description="S3 protocol specific API signature. A decimal string on the wire.",
        examples=[2, 4],
        strict=False,
        title="S3 API signature",
    )

    attributes: list[str] | str | None = Field(
        default=None,
        description=(
            "The custom metadata (HTTP headers). Current providers write their configured"
            " string unchanged; providers using the v0 library write a JSON array of strings."
        ),
        examples=[
            "Cache-Control=max-age=90000,min-fresh=9000;X-Amz-Server-Side-Encryption-Customer-Key=CuStoMerKey=",
            [
                "Cache-Control=max-age=90000",
                "X-Amz-Server-Side-Encryption-Customer-Key=CuStoMerKey=",
            ],
        ],
        title="Custom metadata",
    )

    delete_older_than_days: int | None = Field(
        default=None,
        alias="delete-older-than-days",
        description="Delete objects older than this many days. A decimal string on the wire.",
        examples=[30],
        strict=False,
        title="Delete objects older than (days)",
    )

    data: dict[str, str] | None = Field(
        default=None,
        description=(
            "The requirer's application databag as last seen by the provider, used by the"
            " library to compute diffs. A JSON object on the wire."
        ),
        examples=[{"bucket": "minio", "path": "my/path/"}],
        title="Last seen requirer data",
    )

    @field_serializer("s3_uri_style")
    def _dump_uri_style(self, value: S3URIStyleEnum | None) -> str | None:
        """Write the enum's wire string rather than the enum member."""
        return None if value is None else value.value

    @field_serializer("secret_key")
    def _reveal(self, value: SecretStr | None) -> str | None:
        """Write the real secret to the databag rather than the masked repr."""
        return None if value is None else value.get_secret_value()

    @field_serializer("s3_api_version")
    def _dump_api_version(self, value: S3APIVersion | None) -> str | None:
        """Write the signature as a decimal string; Ops will error on a non-string."""
        return None if value is None else str(value.value)

    @field_serializer("delete_older_than_days")
    def _dump_int(self, value: int | None) -> str | None:
        return None if value is None else str(value)

    @field_validator("tls_ca_chain", "data", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("tls_ca_chain", "data")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    @field_validator("attributes", mode="before")
    @classmethod
    def _load_json_array_or_string(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(loaded, list):
            return cast("list[Any]", loaded)  # Elements are validated by Pydantic.
        return value

    @field_serializer("attributes")
    def _dump_json_array_or_string(self, value: list[str] | str | None) -> str | None:
        if isinstance(value, list):
            return json.dumps(value)
        return value


class RequirerAppData(_BareStringDatabag):
    """Data expected on the requirer side for the s3 v1 interface."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    bucket: str | None = Field(
        default=None,
        description=(
            "The name of the bucket/container requested by the requirer, or the placeholder"
            " relation-<id> written to signal an older provider."
        ),
        examples=["minio", "relation-3"],
        title="Bucket",
    )

    version: str | None = Field(
        default=None,
        description=(
            "The schema version the requirer is using. Absent for requirers that predate it,"
            " which write lib-version or nothing instead."
        ),
        examples=["1"],
        title="Schema version",
    )

    lib_version: str | None = Field(
        default=None,
        alias="lib-version",
        description="The desired S3 lib version the requirer expects. Superseded by version.",
        examples=["1.0"],
        title="S3 lib version",
    )

    path: str | None = Field(
        default=None,
        description="The path inside the bucket/container to store objects.",
        examples=["my/path/"],
        title="Path",
    )

    requested_secrets: list[str] | None = Field(
        default=None,
        alias="requested-secrets",
        description="Any provider field which should be transferred as a Juju Secret. A JSON array on the wire.",
        examples=[["access-key", "secret-key"]],
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


class RequirerUnitData(_BareStringDatabag):
    """The requirer's unit databag, written by the library for its own bookkeeping."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    requested_secrets: list[str] | None = Field(
        default=None,
        alias="requested-secrets",
        description="A copy of requested-secrets from the application databag. A JSON array on the wire.",
        examples=[["access-key", "secret-key"]],
        title="Requested secrets",
    )

    data: dict[str, str] | None = Field(
        default=None,
        description=(
            "The provider's application databag as last seen by the requirer, used by the"
            " library to compute diffs. A JSON object on the wire."
        ),
        examples=[{"bucket": "minio", "endpoint": "https://minio-endpoint/"}],
        title="Last seen provider data",
    )

    @field_validator("requested_secrets", "data", mode="before")
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer("requested_secrets", "data")
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)


ProviderUnitData = None
