"""This file defines the schemas for the provider and requirer sides of this relation interface."""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    """Application databag schema for the provider side of the profiling interface."""

    otlp_grpc_endpoint_url: str = Field(
        description="Grpc ingestion endpoint for profiles using otlp_grpc.",
        examples=["some.hostname:1234", "10.64.140.43:42424"],
    )
    insecure: bool = Field(
        description="Whether the ingestion endpoints should be accessed without TLS (insecure connection).",
        default=False,
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
