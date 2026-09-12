"""This file defines the schemas for the provider and requirer sides of this relation interface."""

import enum
import typing

import pydantic


class MimirRole(str, enum.Enum):
    """Mimir component role names."""

    overrides_exporter = "overrides-exporter"
    query_scheduler = "query-scheduler"
    flusher = "flusher"
    query_frontend = "query-frontend"
    querier = "querier"
    store_gateway = "store-gateway"
    ingester = "ingester"
    distributor = "distributor"
    ruler = "ruler"
    alertmanager = "alertmanager"
    compactor = "compactor"

    # meta-roles
    read = "read"
    write = "write"
    backend = "backend"
    all = "all"


class Scheme(str, enum.Enum):
    """Scheme strings."""

    http = "http"
    https = "https"


class ProviderAppData(pydantic.BaseModel):
    mimir_config: dict[str, typing.Any]


class JujuTopology(pydantic.BaseModel):
    unit: str
    app: str
    charm: str
    model: str
    # in pydantic v2, `model_` is a protected namespace
    juju_model_uuid: str = pydantic.Field(description="Juju model UUID.", alias="model_uuid")


class RequirerUnitData(pydantic.BaseModel):
    juju_topology: JujuTopology
    address: str
    port: int
    scheme: Scheme


class RequirerAppData(pydantic.BaseModel):
    roles: list[MimirRole]


ProviderUnitData = None
