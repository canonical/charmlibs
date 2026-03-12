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

import logging

import ops
from ops import BoundEvent, EventBase
from ops.charm import CharmBase
from ops.framework import Object

from ._schema import BackupTargetEntry, K8sBackupTargetSpec, ProviderAppData

logger = logging.getLogger(__name__)


class K8sBackupTargetRequirer:
    """Requirer class for the backup target configuration relation."""

    def __init__(self, charm: CharmBase, relation_name: str):
        """Initialize the requirer.

        Args:
            charm: The charm instance that requires backup configuration.
            relation_name: The name of the relation (from metadata.yaml).
        """
        self._charm = charm
        self._relation_name = relation_name

    @staticmethod
    def _load_provider_data(relation: ops.Relation) -> ProviderAppData | None:
        """Load and validate provider app data from a relation."""
        try:
            return relation.load(ProviderAppData, relation.app)
        except (ops.RelationDataError, ValueError):
            return None

    @property
    def is_ready(self) -> bool:
        """Check if the relation has valid backup target data.

        Returns:
            True if at least one relation has parseable backup_targets data.
        """
        relations = self._charm.model.relations[self._relation_name]
        for relation in relations:
            data = self._load_provider_data(relation)
            if data and data.backup_targets:
                return True
        return False

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
        relations = self._charm.model.relations[self._relation_name]

        for relation in relations:
            data = self._load_provider_data(relation)
            if not data:
                continue
            for entry in data.backup_targets:
                if (
                    entry.app == app_name
                    and entry.model == model
                    and entry.relation_name == endpoint
                ):
                    return entry.spec

        logger.warning("No backup spec found for app '%s' and endpoint '%s'", app_name, endpoint)
        return None


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
            logger.debug(
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

        entry = BackupTargetEntry(
            app=self._app_name,
            relation_name=self._relation_name,
            model=self._model,
            spec=self._spec,
        )
        provider_data = ProviderAppData(
            backup_targets=[entry],
        )

        for relation in relations:
            relation.save(provider_data, self._charm.app)
