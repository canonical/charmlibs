"""This file defines the schemas for the provider and requirer sides of this relation interface."""

from enum import Enum

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
    worker_config: str = Field(
        description="The tempo configuration that the requirer should run with."
        "Yaml-encoded. Must conform to the schema that the presently deployed "
        "workload version supports; for example see: "
        "https://grafana.com/docs/tempo/latest/configuration/#configure-tempo."
    )
    loki_endpoints: dict[str, str] | None = Field(
        default=None,
        description="List of loki-push-api endpoints to which the worker node can push any logs it generates.",
    )
    ca_cert: str | None = Field(default=None, description="CA certificate for tls encryption.")
    server_cert: str | None = Field(
        default=None, description="Server certificate for tls encryption."
    )
    s3_tls_ca_cert: str | None = Field(
        default=None, description="CA certificate for the s3 bucket API."
    )
    privkey_secret_id: str | None = Field(
        default=None,
        description="ID of a Juju secret that holds the private key used by the coordinator for TLS encryption.",
    )
    remote_write_endpoints: list[dict[str, str]] | None = Field(
        default=None,
        description="Endpoints to which the workload (and the worker charm) can push metrics to.",
    )
    charm_tracing_receivers: dict[str, str] | None = Field(
        default=None,
        description="Endpoints to which the worker node can push its charm traces to."
        "It is a mapping from protocol names such as `zipkin`, `otlp_grpc`, `otlp_http`.",
    )
    workload_tracing_receivers: dict[str, str] | None = Field(
        default=None,
        description="Endpoints to which the worker node can push its workload traces to."
        "It is a mapping from protocol names such as `zipkin`, `otlp_grpc`, `otlp_http`.",
    )
    worker_ports: list[int] | None = Field(
        default=None,
        description="Ports that the worker should open on its pod.",
    )


class _Topology(BaseModel):
    """JujuTopology as defined by cos-lib."""

    application: str
    charm_name: str | None
    unit: str | None


class RequirerUnitData(BaseModel):
    juju_topology: _Topology
    address: str


class TempoRole(str, Enum):
    """Tempo component role names.

    References:
     arch:
      -> https://grafana.com/docs/tempo/latest/operations/architecture/
     config:
      -> https://grafana.com/docs/tempo/latest/configuration/#server
    """

    ALL = "all"  # default, meta-role. gets remapped to scalable-single-binary by the worker.
    QUERIER = "querier"
    QUERY_FRONTEND = "query-frontend"
    INGESTER = "ingester"
    DISTRIBUTOR = "distributor"
    COMPACTOR = "compactor"
    METRICS_GENERATOR = "metrics-generator"


class RequirerAppData(BaseModel):
    role: TempoRole


ProviderUnitData = None
