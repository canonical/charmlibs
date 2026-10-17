"""This file defines the schemas for the provider and requirer sides of the `ip_router` interface.

Examples:
    Provider:
        unit: <empty>
        app: {
              "networks": [
                {
                  "network": "192.168.250.0/24",
                  "gateway": "192.168.250.1",
                  "routes": [
                    {
                      "destination": "172.250.0.0/16",
                      "gateway": "192.168.250.3"
                    }
                  ]
                },
                {
                  "network": "192.168.252.0/24",
                  "gateway": "192.168.252.1",

                },
                {
                  "network": "192.168.251.0/24",
                  "gateway": "192.168.251.1/24"
                }
              ]
            }
    Requirer:
        unit: <empty>
        app:  {
              "networks": [
                {
                  "network": "192.168.250.0/24",
                  "gateway": "192.168.250.1",
                  "routes": [
                    {
                      "destination": "172.250.0.0/16",
                      "gateway": "192.168.250.3"
                    }
                  ]
                }
              ]
            }
"""

from pydantic import BaseModel, Field, IPvAnyAddress, IPvAnyNetwork


class Route(BaseModel):
    destination: IPvAnyAddress
    gateway: IPvAnyAddress


class IPNetwork(BaseModel):
    network: IPvAnyNetwork
    gateway: IPvAnyAddress
    routes: list[Route] | None


class ProviderAppData(BaseModel):
    networks: list[IPNetwork] = Field(
        description="All networks known to the router, with their routes",
        examples=[
            [
                {
                    "network": "192.168.250.0/24",
                    "gateway": "192.168.250.1",
                    "routes": [{"destination": "172.250.0.0", "gateway": "192.168.250.3"}],
                },
                {"network": "192.168.252.0/24", "gateway": "192.168.252.1", "routes": None},
            ]
        ],
    )


class RequirerAppData(BaseModel):
    networks: list[IPNetwork] = Field(
        description="Networks the requirer is attached to, and the routes it needs",
        examples=[
            [
                {
                    "network": "192.168.250.0/24",
                    "gateway": "192.168.250.1",
                    "routes": [{"destination": "172.250.0.0", "gateway": "192.168.250.3"}],
                }
            ]
        ],
    )


ProviderUnitData = None
RequirerUnitData = None
