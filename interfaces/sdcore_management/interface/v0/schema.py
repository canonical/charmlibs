"""This file defines the schemas for the provider and requirer sides of the `sdcore_management` relation interface.

Examples:
    Provider:
        unit: <empty>
        app: {
            "management_endpoint": "http://1.2.3.4:1234",
        }
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field, HttpUrl


class ProviderAppData(BaseModel):
    management_url: HttpUrl = Field(
        description="The endpoint to use to manage SD-Core network.",
        examples=["http://1.2.3.4:1234"],
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
