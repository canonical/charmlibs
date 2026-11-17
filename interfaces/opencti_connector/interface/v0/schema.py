# Copyright 2025 Canonical
# See LICENSE file for licensing details.
"""This file defines the schemas for the provider and requirer sides of the opencti-connector interface.

Examples:
    Provider:
        unit: <empty>
        app: {
                "connector_charm_name": "connector-charm-name",
                "connector_type": "connector-type",
             }

    Requirer:
        unit: <empty>
        app: {
                "opencti_url": "http://opencti-endpoints.stg-opencti.svc:8080",
                "opencti_token": "secret:secret-id",
              }
"""

from pydantic import AnyHttpUrl, BaseModel, Field


class ProviderAppData(BaseModel):
    connector_charm_name: str = Field(
        description="Name of the OpenCTI connector charm.",
        title="Connector Charm Name",
        examples=["opencti-connector-charm"],
    )
    connector_type: str = Field(
        description="Type of the OpenCTI connector.",
        title="Connector Type",
        examples=[
            "EXTERNAL_IMPORT",
            "INTERNAL_ENRICHMENT",
            "INTERNAL_IMPORT_FILE",
            "INTERNAL_EXPORT_FILE",
            "STREAM",
        ],
    )


class RequirerAppData(BaseModel):
    opencti_url: AnyHttpUrl = Field(
        description="URL to the OpenCTI instance.",
        title="OpenCTI URL",
        examples=["http://opencti-endpoints.stg-opencti.svc:8080"],
    )
    opencti_token: str = Field(
        description="Secret token for OpenCTI authentication.",
        title="OpenCTI Token",
        examples=["secret://59060ecc-0495-4a80-8006-5f1fc13fd783/cjqub6vubg2s77p3nio0"],
    )


ProviderUnitData = None
RequirerUnitData = None
