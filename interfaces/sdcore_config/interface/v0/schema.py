"""This file defines the schemas for the provider and requirer sides of the `sdcore_config` relation interface.

Examples:
    Provider:
        unit: <empty>
        app: {
            "webui_url": "sdcore-webui-k8s:9876",
        }
    Requirer:
        unit: <empty>
        app:  <empty>
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    webui_url: str = Field(
        description="GRPC address of the Webui including Webui hostname and a fixed GRPC port.",
        examples=["sdcore-webui-k8s:9876"],
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
