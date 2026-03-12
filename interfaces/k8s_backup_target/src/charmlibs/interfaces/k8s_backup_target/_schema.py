# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Schema models for the k8s_backup_target interface."""

import re

from pydantic import BaseModel, Field

# Regex to check if the provided TTL is a correct duration
DURATION_REGEX = r"^(?=.*\d)(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"

BACKUP_TARGETS_FIELD = "backup_targets"


# This class currently serves as both the public API for defining/reading a backup spec,
# and the databag wire format. They should be decoupled if their needs ever diverge.
class K8sBackupTargetSpec(BaseModel):
    """Backup target configuration specifying what Kubernetes resources to back up.

    Args:
        include_namespaces: Namespaces to include in the backup (None means all).
        include_resources: Resource kinds to include in the backup (None means all).
        exclude_namespaces: Namespaces to exclude from the backup.
        exclude_resources: Resource kinds to exclude from the backup.
        label_selector: Label selector for filtering resources.
        include_cluster_resources:
            Whether to include cluster-scoped resources in the backup.
            Defaults to None (auto detect based on resources).
        ttl: TTL for the backup, if applicable. Example: "24h", "10m10s", etc.
    """

    include_namespaces: list[str] | None = Field(
        default=None,
        description="List of namespaces to include in the backup (None means all namespaces).",
        title="Included Namespaces",
        examples=[["my-namespace"]],
    )
    include_resources: list[str] | None = Field(
        default=None,
        description="List of resource kinds to include (None means all resource types).",
        title="Included Resources",
        examples=[["persistentvolumeclaims", "services", "deployments"]],
    )
    exclude_namespaces: list[str] | None = Field(
        default=None,
        description="List of namespaces to exclude from the backup.",
        title="Excluded Namespaces",
        examples=[["default"]],
    )
    exclude_resources: list[str] | None = Field(
        default=None,
        description="List of resource kinds to exclude from the backup.",
        title="Excluded Resources",
        examples=[["pods"]],
    )
    include_cluster_resources: bool | None = Field(
        default=None,
        description="Whether to include cluster-scoped resources in the backup.",
        title="Include Cluster Resources",
        examples=[True],
    )
    label_selector: dict[str, str] | None = Field(
        default=None,
        description="Label selector to filter resources for backup.",
        title="Label Selector",
        examples=[{"app": "my-app"}],
    )
    ttl: str | None = Field(
        default=None,
        description="Optional TTL (time-to-live) for the backup (e.g. '72h' or '30d').",
        title="Backup TTL",
        examples=["24h"],
    )

    def __post_init__(self):
        """Validate the specification."""
        if self.ttl and not re.match(DURATION_REGEX, self.ttl):
            raise ValueError(
                f"Invalid TTL format: {self.ttl}. Expected format: '24h', '10h10m10s', etc."
            )


class BackupTargetEntry(BaseModel):
    """A single backup target entry in the collection."""

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
    spec: K8sBackupTargetSpec = Field(
        ...,
        description="Backup specification details (namespaces, resources, etc.).",
        title="Backup Target Spec",
    )


class ProviderAppData(BaseModel):
    """Pydantic model for the provider's application databag."""

    backup_targets: list[BackupTargetEntry] = Field(
        ...,
        description="List of backup target entries.",
        title="Backup Targets",
    )
