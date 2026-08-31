"""This file defines the schemas for the provider and requirer sides of the `certificate_transfer` interface.

Examples:
    Provider:
        unit: <empty>
        app: {
            "certificates": [
                "-----BEGIN CERTIFICATE----- ...",
                "-----BEGIN CERTIFICATE----- ..."
            ]
        }
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    certificates: set[str] = Field(
        description="The set of certificates that will be transferred to a requirer"
    )
    version: int = Field(
        description="The version of the interface used in this databag", default=1
    )


class RequirerAppData(BaseModel):
    version: int = Field(
        description="The version of the interface used by this requirer", default=1
    )


ProviderUnitData = None
RequirerUnitData = None
