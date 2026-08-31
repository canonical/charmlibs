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
              "name": "app-name",
              "host": "hostname"
              }
        app: {
              "port": 4242,
              "model": "model-name"
              }
"""

from pydantic import AnyHttpUrl, BaseModel, Field


class Url(BaseModel):
    url: AnyHttpUrl


class ProviderAppData(BaseModel):
    ingress: Url


class RequirerAppData(BaseModel):
    model: str = Field(description="The model the application is in.")
    port: int = Field(description="The port the unit wishes to be exposed. Stringified int.")
    name: str = Field(description="The name of the application requesting ingress.")


class RequirerUnitData(BaseModel):
    host: str = Field(description="Unit hostname to be exposed.")


ProviderUnitData = None
