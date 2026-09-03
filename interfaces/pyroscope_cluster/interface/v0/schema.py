"""This file defines the schemas for the provider and requirer sides of this relation interface."""

from enum import Enum

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class RemoteWriteEndpoint(TypedDict):
    """Type of the remote write endpoints to be passed to the worker through cluster relation data."""

    url: str


class ProviderAppData(BaseModel):
    worker_config: str = Field(
        description="The pyroscope configuration that the requirer should run with."
        "Yaml-encoded. Must conform to the schema that the presently deployed "
        "workload version supports; for example see: "
        "https://grafana.com/docs/pyroscope/latest/configuration/#configure-pyroscope."
    )
    loki_endpoints: dict[str, str] | None = Field(
        default=None,
        description="List of loki-push-api endpoints to which the worker node can push any logs it generates.",
    )
    charm_tracing_receivers: dict[str, str] | None = Field(
        default=None,
        description="Endpoints to which the the worker can push charm traces to.",
    )
    workload_tracing_receivers: dict[str, str] | None = Field(
        default=None,
        description="Endpoints to which the the worker can push workload traces to.",
    )
    remote_write_endpoints: list[RemoteWriteEndpoint] | None = Field(
        default=None,
        description="Endpoints to which the workload (and the worker charm) can push metrics to.",
    )
    worker_ports: list[int] | None = Field(
        default=None,
        description="Ports that the worker should open. "
        "If not provided, the worker will open all the legacy ones.",
    )
    ca_cert: str | None = Field(default=None, description="CA certificate for tls encryption.")
    server_cert: str | None = Field(
        default=None, description="Server certificate for tls encryption."
    )
    privkey_secret_id: str | None = Field(
        default=None,
        description="Private key used by the coordinator, for tls encryption.",
    )
    s3_tls_ca_chain: str | None = Field(
        default=None,
        description="CA chain to use to validate traffic with the s3 endpoint.",
    )


class _Topology(BaseModel):
    """JujuTopology as defined by cos-lib."""

    application: str
    charm_name: str | None
    unit: str | None


class RequirerUnitData(BaseModel):
    juju_topology: _Topology
    address: str


class PyroscopeRole(str, Enum):
    """Pyroscope component role names.

    References:
     arch:
      -> https://grafana.com/docs/pyroscope/latest/reference-pyroscope-architecture/
     config:
      -> https://grafana.com/docs/pyroscope/latest/configure-server/
    """

    all = "all"  # default, meta-role.

    querier = "querier"
    query_frontend = "query-frontend"
    query_scheduler = "query-scheduler"
    ingester = "ingester"
    distributor = "distributor"
    compactor = "compactor"
    store_gateway = "store-gateway"


class RequirerAppData(BaseModel):
    role: PyroscopeRole


ProviderUnitData = None
