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

from pydantic import BaseModel


class ProviderAppData(BaseModel):
    upf_ip_address: str


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
