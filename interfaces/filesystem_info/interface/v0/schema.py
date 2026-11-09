"""This file defines the schemas for the provider and requirer sides of the filesystem_info interface.
It defines one model, `ProviderAppData`.
Examples:
    Provider:
        app: {
            "endpoint": "nfs://(192.168.1.1:65535)/export"
        }
        unit: <empty>
    Requirer:
        unit: <empty>
        app: <empty>
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    """App databag model for the `filesystem_info` interface."""

    endpoint: str = Field(
        description="Endpoint information to mount the exported filesystem.",
        examples=[
            "nfs://(192.168.1.1:65535)/export",
            "lustre://(192.168.227.11%40tcp1,192.168.227.12%40tcp1)/export",
            "cephfs://fsuser@(192.168.1.1,192.168.1.2,192.168.1.3)/export?fsid=asdf1234&auth=secret%3AYXNkZnF3ZXJhc2RmcXdlcmFzZGZxd2Vy&filesystem=scratch",
        ],
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
