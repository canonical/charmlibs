# Copyright 2025 Canonical
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
        description="Comma separated list of etcd endpoints",
        title="etcd Endpoints",
        examples=["etcd1:2379,etcd2:2379"],
    )

    version: str = Field(
        description="etcd version",
        title="etcd Version",
        examples=["3.5.18"],
    )

    secret_tls: str = Field(
        alias="secret-tls",
        description="Secret URI containing the tls-ca",
        title="TLS Secret URI",
        examples=["secret://12312323112313123213"],
    )

    secret_user: str = Field(
        alias="secret-user",
        description="Secret URI containing the etcd user information",
        title="User Secret URI",
        examples=["secret://12312323112313123213"],
    )


class RequirerAppData(_BareStringDatabag):
    """The requirer's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    prefix: str = Field(
        description="The prefix of the range of keys requested",
        title="Key Prefix",
        examples=["/my/keys"],
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
        examples='["username", "uris", "tls", "tls-ca"]',
    )

    provided_secrets: str = Field(
        alias="provided-secrets",
        description="The fields provided as secrets. A JSON array on the wire.",
        title="Provided Secrets",
        examples='["mtls-cert"]',
    )


ProviderUnitData = None
RequirerUnitData = None
