"""This file defines the schemas for the provider and requirer sides of the `fiveg_n4` interface.

Examples:

    Provider:
        unit: <empty>
        app: {
            "upf_hostname": "upf.uplane-cloud.canonical.com",
            "upf_port": 8805
        }

    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    upf_hostname: str = Field(
        description="Name of the host exposing the UPF's N4 interface.",
        examples=["upf.uplane-cloud.canonical.com"],
    )
    upf_port: int = Field(
        description="Port on which UPF's N4 interface is exposed.", examples=[8805]
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
