# Copyright 2026 Canonical
# See LICENSE file for licensing details.

from pydantic import BaseModel, ConfigDict, Field


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
        description="Comma separated list of Valkey read/write endpoints",
        title="Valkey Endpoints",
        examples=["valkey-1.valkey-endpoints:6379"],
    )

    read_only_endpoints: str = Field(
        alias="read-only-endpoints",
        description="Comma separated list of Valkey read-only endpoints",
        title="Valkey read-only Endpoints",
        examples=["valkey-0.valkey-endpoints:6379,valkey-2.valkey-endpoints:6379"],
    )

    sentinel_endpoints: str = Field(
        description="Comma separated list of Valkey Sentinel endpoints",
        title="Sentinel Endpoints",
        examples=[
            "valkey-0.valkey-endpoints:26379,valkey-1.valkey-endpoints:26379,valkey-2.valkey-endpoints:26379"
        ],
    )

    mode: str = Field(
        description="Valkey High Availability mode",
        title="Valkey HA mode",
        examples=["sentinel"],
    )

    version: str = Field(
        description="Valkey version",
        title="Valkey Version",
        examples=["9.0.1"],
    )

    secret_tls: str = Field(
        alias="secret-tls",
        description="Secret URI containing the tls-ca",
        title="TLS Secret URI",
        examples=["secret://12312323112313123213"],
    )

    secret_user: str = Field(
        alias="secret-user",
        description="Secret URI containing the Valkey user information",
        title="User Secret URI",
        examples=["secret://12312323112313123213"],
    )


class RequirerAppData(_BareStringDatabag):
    """The requirer's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    resource: str = Field(
        description="The prefix of the range of keys requested",
        title="Key Prefix",
        examples=["my_keys:*"],
    )

    secret_mtls: str = Field(
        alias="secret-mtls",
        description="Secret URI containing the client certificate",
        title="mTLS Secret URI",
        examples=["secret://12312323112313123213"],
    )

    requested_secrets: str = Field(
        alias="requested-secrets",
        description="The fields required to be a secret. A JSON array on the wire.",
        title="Requested Secrets",
        examples='["username", "password", "tls", "tls-ca"]',
    )


ProviderUnitData = None
RequirerUnitData = None
