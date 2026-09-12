"""This file defines the schemas for the provider and requirer sides of the `fiveg_rfsim` interface.

Examples:
    Provider:
        unit: <empty>
        app: {
            "rfsim_address": "192.168.70.130",
            "sst": 1,
            "sd": 1,
        }
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    rfsim_address: str = Field(description="RF simulator service ip", examples=["192.168.70.130"])
    sst: int = Field(
        description="Slice/Service Type",
        examples=[1, 2, 3, 4],
        ge=0,
        le=255,
    )
    sd: int | None = Field(
        description="Slice Differentiator",
        default=None,
        examples=[1],
        ge=0,
        le=16777215,
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
