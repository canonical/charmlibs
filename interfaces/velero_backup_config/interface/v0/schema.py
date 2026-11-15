# Copyright 2025 Canonical
# See LICENSE file for licensing details.


from pydantic import BaseModel, Field


class VeleroBackupSpec(BaseModel):
    """Pydantic model for the backup specification details."""

    include_namespaces: list[str] | None = Field(
        None,
        alias="include-namespaces",
        description="List of namespaces to include in the backup (None means all namespaces).",
        title="Included Namespaces",
        examples=[["kubeflow"]],
    )
    include_resources: list[str] | None = Field(
        None,
        alias="include-resources",
        description="List of resource kinds to include (None means all resource types).",
        title="Included Resources",
        examples=[["profiles.kubeflow.org", "deployments"]],
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
    include_cluster_resources: bool = Field(
        False,
        alias="include-cluster-resources",
        description="Whether to include cluster-scoped resources in the backup.",
        title="Include Cluster Resources",
        examples=[True],
    )
    label_selector: dict[str, str] | None = Field(
        None,
        alias="label-selector",
        description="Label selector to filter resources for backup (e.g. {'app': 'kubeflow'}).",
        title="Label Selector",
        examples=[{"app": "kubeflow"}],
    )
    ttl: str | None = Field(
        None,
        description="Optional TTL (time-to-live) for the backup (e.g. '72h' or '30d').",
        title="Backup TTL",
        examples=["24h"],
    )


class RequirerAppData(BaseModel):
    """Pydantic model for the requirer's application databag."""

    app: str = Field(
        ...,
        description="Name of the client application requesting backup.",
        title="Client Application Name",
        examples=["kubeflow"],
    )
    relation_name: str = Field(
        ...,
        description="Name of the relation on the client providing this spec.",
        title="Client Relation Name",
        examples=["profiles-backup"],
    )
    model: str = Field(
        ...,
        description="Model name of the client application.",
        title="Client Model Name",
        examples=["kubeflow-model"],
    )
    spec: VeleroBackupSpec = Field(
        ...,
        description="Backup specification details (namespaces, resources, etc.).",
        title="Velero Backup Spec",
    )


ProviderAppData = None
ProviderUnitData = None
RequirerUnitData = None
