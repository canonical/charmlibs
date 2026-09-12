"""This file defines the schemas for the provider and requirer sides of the `fiveg_n2` interface.

Examples:
    Provider:
        unit: <empty>
        app: {
            "amf_ip_address": "192.168.70.132",
            "amf_hostname": "amf",
            "amf_port": 38412
        }
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field, IPvAnyAddress


class ProviderAppData(BaseModel):
    amf_ip_address: IPvAnyAddress = Field(
        description="IP Address to reach the AMF's N2 interface.", examples=["192.168.70.132"]
    )
    amf_hostname: str = Field(
        description="Hostname to reach the AMF's N2 interface.", examples=["amf"]
    )
    amf_port: int = Field(description="Port to reach the AMF's N2 interface.", examples=[38412])


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
