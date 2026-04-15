# Copyright 2026 Canonical
# See LICENSE file for licensing details.

from interface_tester.schema_base import DataBagSchema
from pydantic import Field


class ProviderSchema(DataBagSchema):
    """The schema for the provider side of this interface."""

    endpoints: str = Field(
        description="Comma separated list of Valkey read/write endpoints",
        title="Valkey Endpoints",
        examples=["valkey-1.valkey-endpoints:6379"],
    )

    read_only_endpoints: str = Field(
        description="Comma separated list of Valkey read-only endpoints",
        title="Valkey read-only Endpoints",
        examples=["valkey-0.valkey-endpoints:6379,valkey-2.valkey-endpoints:6379"],
    )

    sentinel_endpoints: str = Field(
        description="Comma separated list of Valkey Sentinel endpoints",
        title="Sentinel Endpoints",
        examples=["valkey-0.valkey-endpoints:26379,valkey-1.valkey-endpoints:26379,valkey-2.valkey-endpoints:26379"],
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
        description="Secret URI containing the tls-ca",
        title="TLS Secret URI",
        examples=["secret://12312323112313123213"],
    )

    secret_user: str = Field(
        description="Secret URI containing the Valkey user information",
        title="User Secret URI",
        examples=["secret://12312323112313123213"],
    )


class RequirerSchema(DataBagSchema):
    """The schema for the requirer side of this interface."""

    resource: str = Field(
        description="The prefix of the range of keys requested",
        title="Key Prefix",
        examples=["my_keys:*"],
    )

    secret_mtls: str = Field(
        description="Secret URI containing the client certificate",
        title="mTLS Secret URI",
        examples=["secret://12312323112313123213"],
    )

    requested_secrets: str = Field(
        description="The fields required to be a secret.",
        title="Requested Secrets",
        examples='["username", "password", "tls", "tls-ca"]',
    )
