# Copyright 2023 Canonical
# See LICENSE file for licensing details.
"""This file defines the schemas for the provider and requirer sides of the ingress interface.

Examples:
    Provider:
        unit: <empty>
        app: {"ingress":
                 {"url":  "http://foo.bar:80/model_name-app_name"}
             }

    Requirer:
        unit: {
              "host": "hostname"
              }
        app: {
              "name": "app-name",
              "port": 4242,
              "model": "model-name"
              }
"""

from pydantic import AnyHttpUrl, BaseModel, Field


class Url(BaseModel):
    url: AnyHttpUrl


class ProviderAppData(BaseModel):
    ingress: Url


class HealthCheck(BaseModel):
    path: str = Field(description="The health check endpoint path.")
    scheme: str | None = Field(
        default=None, description="Replaces the server URL scheme for the health check endpoint."
    )
    hostname: str | None = Field(
        default=None, description="Hostname to be set in the health check request."
    )
    port: int | None = Field(
        default=None, description="Replaces the server URL port for the health check endpoint."
    )
    interval: str = Field(default="30s", description="Frequency of the health check calls.")
    timeout: str = Field(default="5s", description="Maximum duration for a health check request.")


class RequirerAppData(BaseModel):
    model: str = Field(description="The model the application is in.")
    port: int = Field(description="The port the unit wishes to be exposed. Stringified int.")
    name: str = Field(description="The name of the application requesting ingress.")
    is_port_open: bool = Field(default=False, description="Whether the port is open.")
    healthcheck_params: HealthCheck | None = Field(
        default=None, description="Optional health check configuration for ingress."
    )


class RequirerUnitData(BaseModel):
    host: str = Field(description="Unit hostname to be exposed.")
    ip: str | None = Field(
        default=None,
        description="IP address at which the unit is reachable, if Juju provides one.",
    )


ProviderUnitData = None
