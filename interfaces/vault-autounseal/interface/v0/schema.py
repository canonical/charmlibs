"""This file defines the schemas for the provider and requirer sides of this relation interface."""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    """Provider side of the vault-autounseal relation interface."""

    address: str = Field(description="The address of the Vault server to connect to.")
    mount_path: str = Field(
        description="The path to the transit engine mount point where the autounseal keys are stored."
    )
    key_name: str = Field(description="The name of the key to use for autounseal.")
    credentials_secret_id: str = Field(
        description=(
            "The secret id of the Juju secret which stores the credentials for authenticating with the Vault server."
        )
    )
    ca_certificate: str = Field(
        description="The CA certificate to use when validating the Vault server's certificate."
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
