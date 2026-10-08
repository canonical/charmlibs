# Copyright 2023 Canonical
# See LICENSE file for licensing details.
"""This file defines the schema for the provider side of the milter interface.

Examples:
    Provider:
        app: <empty>
        unit:
          port: 8892
"""

from pydantic import BaseModel, Field


class ProviderUnitData(BaseModel):
    port: int = Field(
        ge=1,
        le=65536,
        description="Milter port.",
        title="Port",
        examples=[8892, 8893],
    )


ProviderAppData = None
RequirerAppData = None
RequirerUnitData = None
