# Copyright 2025 Canonical Ltd.
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

"""Gateway metadata interface implementation.

Migrated from charmed-service-mesh-helpers interfaces/gateway_metadata.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ops.framework import Object
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from ops import CharmBase

logger = logging.getLogger(__name__)


class GatewayMetadata(BaseModel):
    """Gateway workload metadata.

    Attributes:
        namespace: Kubernetes namespace where the Gateway is deployed.
        gateway_name: Name of the Gateway resource.
        deployment_name: Name of the Deployment managing the Gateway workload.
        service_account: Name of the ServiceAccount used by the Gateway workload.
    """

    model_config = ConfigDict(frozen=True)

    namespace: str = Field(description='Kubernetes namespace')
    gateway_name: str = Field(description='Gateway resource name')
    deployment_name: str = Field(description='Deployment name')
    service_account: str = Field(description='ServiceAccount name')


class GatewayMetadataProvider(Object):
    """Provider side of the gateway-metadata interface.

    The provider publishes metadata about the Gateway workload to related applications.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = 'gateway-metadata',
    ):
        """Initialize the GatewayMetadataProvider.

        Args:
            charm: The charm that owns this provider.
            relation_name: Name of the relation (default: "gateway-metadata").
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    def publish_metadata(self, metadata: GatewayMetadata) -> None:
        """Publish gateway metadata to all related applications.

        Args:
            metadata: The GatewayMetadata to publish.
        """
        if not self._charm.unit.is_leader():
            logger.debug('Not leader, skipping metadata publication')
            return

        relations = self._charm.model.relations[self._relation_name]

        for relation in relations:
            relation.data[self._charm.app]['metadata'] = metadata.model_dump_json()


class GatewayMetadataRequirer(Object):
    """Requirer side of the gateway-metadata interface.

    The requirer receives metadata about the Gateway workload from the provider.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = 'gateway-metadata',
    ):
        """Initialize the GatewayMetadataRequirer.

        Args:
            charm: The charm that owns this requirer.
            relation_name: Name of the relation (default: "gateway-metadata").
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    @property
    def is_ready(self) -> bool:
        """Check if gateway metadata is available.

        Returns:
            True if the provider has published metadata, False otherwise.
        """
        relation = self._get_relation()
        if not relation or not relation.app:
            return False

        metadata_json = relation.data[relation.app].get('metadata')
        if not metadata_json:
            return False

        return True

    def get_metadata(self) -> GatewayMetadata | None:
        """Retrieve the gateway metadata published by the provider.

        Returns:
            GatewayMetadata if available, None otherwise.
        """
        if not self.is_ready:
            return None

        relation = self._get_relation()
        metadata_json = relation.data[relation.app].get('metadata')  # type: ignore[union-attr]

        try:
            return GatewayMetadata.model_validate_json(metadata_json)  # type: ignore[arg-type]
        except Exception:
            logger.exception('Failed to parse metadata from %s', relation)
            return None

    def _get_relation(self):
        """Get the gateway-metadata relation.

        Returns:
            The first gateway-metadata relation, or None if no relation exists.
        """
        relations = self._charm.model.relations[self._relation_name]
        return relations[0] if relations else None
