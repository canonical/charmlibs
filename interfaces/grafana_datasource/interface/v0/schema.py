from typing import Any

from pydantic import BaseModel, Field


class GrafanaSourceData(BaseModel):
    model: str = Field(
        description="Name of the Juju model where the source is deployed.", examples=['cos']
    )
    model_uuid: str = Field(
        description="UUID of the Juju model where the source is deployed.",
        examples=["0000-0000-0000-0000"],
    )
    application: str = Field(
        description="Name of the Juju model where the source is deployed.",
        examples=['tempo', 'loki', 'prometheus'],
    )
    type: str = Field(
        description="Type of the datasource.", examples=['tempo', 'loki', 'prometheus']
    )
    extra_fields: Any | None = Field(
        description="Any datasource-type-specific additional configuration."
    )
    secure_extra_fields: Any | None = Field(
        description="Any secure datasource-type-specific additional configuration."
    )


class ProviderAppData(BaseModel):
    """Application databag model for the requirer side of this interface."""

    grafana_source_data: GrafanaSourceData


class ProviderUnitData(BaseModel):
    """Application databag model for the requirer side of this interface."""

    grafana_source_host: str = Field(
        description="Hostname of a source server.", examples=['localhost:80']
    )


class RequirerAppData(BaseModel):
    """Application databag model for the requirer side of this interface."""

    datasource_uids: dict[str, str]
    grafana_uid: str = Field(
        description="UID of the requirer application.",
        examples=['foo-0000-0000-0000-0000-grafana-1'],
    )


RequirerUnitData = None
