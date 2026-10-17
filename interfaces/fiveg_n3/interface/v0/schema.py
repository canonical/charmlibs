"""This file defines the schemas for the provider and requirer sides of the `fiveg_n3` interface.

Examples:
    Provider:
        unit: <empty>
        app: {
            "upf_ip_address": "1.2.3.4"
        }
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    upf_ip_address: str = Field(
        description="IP address of the UPF's N3 interface",
        examples=["192.168.252.3"],
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
