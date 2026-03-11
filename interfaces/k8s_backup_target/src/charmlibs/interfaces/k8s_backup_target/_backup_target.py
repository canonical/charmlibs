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

"""K8s Backup Target library implementation."""

import json
import logging
import re
from typing import cast

from ops import BoundEvent, EventBase
from ops.charm import CharmBase
from ops.framework import Object
from pydantic import BaseModel, ValidationError

# Regex to check if the provided TTL is a correct duration
DURATION_REGEX = r"^(?=.*\d)(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"

BACKUP_TARGETS_FIELD = "backup_targets"

logger = logging.getLogger(__name__)


class K8sBackupTargetSpec(BaseModel):
    """Dataclass representing the backup target configuration.

    Args:
        include_namespaces: Namespaces to include in the backup.
        include_resources: Resources to include in the backup.
        exclude_namespaces: Namespaces to exclude from the backup.
        exclude_resources: Resources to exclude from the backup.
        label_selector: Label selector for filtering resources.
        include_cluster_resources:
            Whether to include cluster-wide resources in the backup.
            Defaults to None (auto detect based on resources).
        ttl: TTL for the backup, if applicable. Example: "24h", "10m10s", etc.
    """

    include_namespaces: list[str] | None = None
    include_resources: list[str] | None = None
    exclude_namespaces: list[str] | None = None
    exclude_resources: list[str] | None = None
    label_selector: dict[str, str] | None = None
    ttl: str | None = None
    include_cluster_resources: bool | None = None

    def __post_init__(self):
        """Validate the specification."""
        if self.ttl and not re.match(DURATION_REGEX, self.ttl):
            raise ValueError(
                f"Invalid TTL format: {self.ttl}. Expected format: '24h', '10h10m10s', etc."
            )


class _BackupTargetEntry(BaseModel):
    """Internal model for a single backup target entry on the wire."""

    app: str
    relation_name: str
    model: str
    spec: K8sBackupTargetSpec


class K8sBackupTargetRequirer(Object):
    """Requirer class for the backup target configuration relation."""

    def __init__(self, charm: CharmBase, relation_name: str):
        """Initialize the requirer.

        Args:
            charm: The charm instance that requires backup configuration.
            relation_name: The name of the relation (from metadata.yaml).
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    @property
    def is_ready(self) -> bool:
        """Check if the relation has valid backup target data.

        Returns:
            True if at least one relation has parseable backup_targets data.
        """
        relations = self.model.relations[self._relation_name]
        for relation in relations:
            data = relation.data.get(relation.app, {})
            raw = data.get(BACKUP_TARGETS_FIELD)
            if not raw:
                continue
            if self._parse_backup_targets(raw):
                return True
        return False

    def _parse_backup_targets(self, raw: str) -> list[_BackupTargetEntry]:
        """Parse the backup_targets JSON string, returning validated entries."""
        try:
            parsed: object = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse backup_targets data: %s", raw)
            return []

        if not isinstance(parsed, list):
            logger.warning("Expected a list for backup_targets, got: %s", type(parsed).__name__)
            return []

        raw_entries = cast("list[object]", parsed)
        entries: list[_BackupTargetEntry] = []
        for raw_entry in raw_entries:
            entry = self._validate_entry(raw_entry)
            if entry is not None:
                entries.append(entry)
        return entries

    @staticmethod
    def _validate_entry(raw_entry: object) -> _BackupTargetEntry | None:
        """Validate a single raw entry dict into a _BackupTargetEntry."""
        try:
            return _BackupTargetEntry.model_validate(raw_entry)
        except ValidationError:
            logger.warning("Skipping invalid backup target entry: %s", raw_entry)
            return None

    def get_backup_spec(
        self, app_name: str, endpoint: str, model: str
    ) -> K8sBackupTargetSpec | None:
        """Get a K8sBackupTargetSpec for a given (app, endpoint, model).

        Args:
            app_name: The name of the application for which the backup is configured.
            endpoint: The name of the relation (from metadata.yaml).
            model: The model name of the application.

        Returns:
            The backup specification if available, otherwise None.
        """
        relations = self.model.relations[self._relation_name]

        for relation in relations:
            data = relation.data.get(relation.app, {})
            raw = data.get(BACKUP_TARGETS_FIELD)
            if not raw:
                continue
            for entry in self._parse_backup_targets(raw):
                if (
                    entry.app == app_name
                    and entry.model == model
                    and entry.relation_name == endpoint
                ):
                    return entry.spec

        logger.warning("No backup spec found for app '%s' and endpoint '%s'", app_name, endpoint)
        return None

    def get_all_backup_specs(self) -> list[K8sBackupTargetSpec]:
        """Get a list of all active K8sBackupTargetSpec objects across all relations.

        Returns:
            A list of all active backup specifications.
        """
        specs: list[K8sBackupTargetSpec] = []
        relations = self.model.relations[self._relation_name]

        for relation in relations:
            data = relation.data.get(relation.app, {})
            raw = data.get(BACKUP_TARGETS_FIELD)
            if not raw:
                continue
            specs.extend(entry.spec for entry in self._parse_backup_targets(raw))

        return specs


class K8sBackupTargetProvider(Object):
    """Provider class for the backup target configuration relation."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        spec: K8sBackupTargetSpec,
        refresh_event: BoundEvent | list[BoundEvent] | None = None,
    ):
        """Initialize the provider with the specified backup configuration.

        Args:
            charm: The charm instance that provides backup.
            relation_name: The name of the relation (from metadata.yaml).
            spec: The backup specification to be used.
            refresh_event: Optional event(s) to trigger data sending.
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._app_name = self._charm.app.name
        self._model = self._charm.model.name
        self._relation_name = relation_name
        self._spec = spec

        self.framework.observe(self._charm.on.leader_elected, self._send_data)
        self.framework.observe(
            self._charm.on[self._relation_name].relation_created, self._send_data
        )
        self.framework.observe(self._charm.on.upgrade_charm, self._send_data)

        if refresh_event:
            if not isinstance(refresh_event, tuple | list):
                refresh_event = [refresh_event]
            for event in refresh_event:
                self.framework.observe(event, self._send_data)

    def _send_data(self, event: EventBase):
        """Handle any event where we should send data to the relation."""
        if not self._charm.model.unit.is_leader():
            logger.warning(
                "K8sBackupTargetProvider handled send_data event when it is not a leader. "
                "Skipping event - no data sent"
            )
            return

        relations = self._charm.model.relations.get(self._relation_name)

        if not relations:
            logger.warning(
                "K8sBackupTargetProvider handled send_data event but no relation '%s' found. "
                "Skipping event - no data sent",
                self._relation_name,
            )
            return

        entry = {
            "app": self._app_name,
            "relation_name": self._relation_name,
            "model": self._model,
            "spec": self._spec.model_dump(exclude_none=True),
        }
        backup_targets_json = json.dumps([entry], sort_keys=True)

        for relation in relations:
            relation.data[self._charm.app].update({
                BACKUP_TARGETS_FIELD: backup_targets_json,
            })
