"""This file defines the schemas for the provider and requirer sides of the `fiveg_nrf` interface.

Examples:
    Provider:
        unit: <empty>
        app: {"url": "https://nrf-example.com:1234"}
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import AnyHttpUrl, BaseModel, Field


class ProviderAppData(BaseModel):
    url: AnyHttpUrl = Field(
        description="url to reach the NRF.", examples=["https://nrf-example.com:1234"]
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
