"""This file defines the schemas for the provider and requirer sides of the `fiveg_gnb_identity` relation interface.

Examples:
    Provider:
        unit: <empty>
        app: {
            "gnb_name": "gnb001",
            "tac": 1
        }
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    gnb_name: str = Field(description="Name of the gnB.", examples=["gnb001"])
    tac: int = Field(description="Tracking Area Code", examples=[1])


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
