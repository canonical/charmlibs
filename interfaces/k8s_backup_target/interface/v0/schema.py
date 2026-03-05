# Copyright 2026 Canonical
# See LICENSE file for licensing details.


from interface_tester.schema_base import DataBagSchema
from pydantic import BaseModel, Field


class BackupTargetSpec(BaseModel):
    """Pydantic model for the backup specification details."""

    include_namespaces: list[str] | None = Field(
        None,
        alias="include-namespaces",
        description="List of namespaces to include in the backup (None means all namespaces).",
        title="Included Namespaces",
        examples=[["my-namespace"]],
    )
    include_resources: list[str] | None = Field(
        None,
        alias="include-resources",
        description="List of resource kinds to include (None means all resource types).",
        title="Included Resources",
        examples=[["persistentvolumeclaims", "services", "deployments"]],
    )
    exclude_namespaces: list[str] | None = Field(
        None,
        alias="exclude-namespaces",
        description="List of namespaces to exclude from the backup.",
        title="Excluded Namespaces",
        examples=[["default"]],
    )
    exclude_resources: list[str] | None = Field(
        None,
        alias="exclude-resources",
        description="List of resource kinds to exclude from the backup.",
        title="Excluded Resources",
        examples=[["pods"]],
    )
    include_cluster_resources: bool | None = Field(
        None,
        alias="include-cluster-resources",
        description="Whether to include cluster-scoped resources in the backup.",
        title="Include Cluster Resources",
        examples=[True],
    )
    label_selector: dict[str, str] | None = Field(
        None,
        alias="label-selector",
        description="Label selector to filter resources for backup.",
        title="Label Selector",
        examples=[{"app": "my-app"}],
    )
    ttl: str | None = Field(
        None,
        description="Optional TTL (time-to-live) for the backup (e.g. '72h' or '30d').",
        title="Backup TTL",
        examples=["24h"],
    )


class ProviderAppData(BaseModel):
    """Pydantic model for the provider's application databag."""

    app: str = Field(
        ...,
        description="Name of the client application requesting backup.",
        title="Client Application Name",
        examples=["my-app"],
    )
    relation_name: str = Field(
        ...,
        description="Name of the relation on the client providing this spec.",
        title="Client Relation Name",
        examples=["backup"],
    )
    model: str = Field(
        ...,
        description="Model name of the client application.",
        title="Client Model Name",
        examples=["my-model"],
    )
    spec: BackupTargetSpec = Field(
        ...,
        description="Backup specification details (namespaces, resources, etc.).",
        title="Backup Target Spec",
    )


class ProviderSchema(DataBagSchema):
    """Schema for the provider (client) side of k8s_backup_target."""

    app: ProviderAppData


class RequirerSchema(DataBagSchema):
    """Schema for the requirer (backup integrator) side of k8s_backup_target."""

    # The requirer sends no data, so no app or unit fields are defined.
    pass
