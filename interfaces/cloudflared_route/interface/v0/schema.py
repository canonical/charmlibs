# Copyright 2024 Canonical
# See LICENSE file for licensing details.
"""This file defines the schemas for the provider sides of the cloudflared_route interface.

Examples:
    Provider:
        unit: <empty>
        app: {
          "tunnel_token_secret_id": "secret:csn5caau557j9bojn7rg",
          "nameserver": "1.1.1.1"
        }
"""

from pydantic import BaseModel, IPvAnyAddress


class ProviderAppData(BaseModel):
    """Provider application databag schema for cloudflared_route integration."""

    tunnel_token_secret_id: str
    nameserver: IPvAnyAddress | None = None


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
