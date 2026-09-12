"""This file defines the schemas for the provider and requirer sides of this relation interface."""

from collections.abc import Mapping

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    vault_url: str = Field(description="The URL of the Vault server to connect to.")
    mount: str = Field(
        description=(
            "The KV mount available for the requirer application, "
            "respecting the pattern 'charm-<requirer app>-<user provided suffix>'."
        )
    )
    ca_certificate: str = Field(
        description="The CA certificate to use when validating the Vault server's certificate."
    )
    credentials: Mapping[str, str] = Field(
        description=(
            "Mapping of unit name and credentials for that unit."
            " Credentials are a juju secret containing a 'role-id' and a 'role-secret-id'."
            " In case of wrap_ttl being requested, 'role-secret-id' will be empty and"
            " 'wrapping-token' will contain the role-secret-id as a response-wrapping token."
        )
    )


class RequirerAppData(BaseModel):
    mount_suffix: str = Field(
        description="Suffix to append to the mount name to get the KV mount."
    )
    wrap_ttl: int | None = Field(
        default=None,
        title="Wrap TTL",
        description=(
            "Whether to request approle secret_id as a response-wrapping token with a certain TTL."
            " If not set, no wrapping will be made to secret_id. Otherwise, wrap_ttl specifies"
            " the duration of seconds before the expiration of the response-wrapping token."
        ),
    )


class RequirerUnitData(BaseModel):
    egress_subnet: str = Field(
        description="A string of egress subnets separated by commas, in CIDR notation."
    )
    nonce: str = Field(
        description=(
            "Uniquely identifying value for this unit. `secrets.token_hex(16)` is recommended."
        )
    )


ProviderUnitData = None
