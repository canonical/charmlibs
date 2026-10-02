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

"""Istio metadata interface implementation.

Migrated from `charms.istio_k8s.v0.istio_metadata` in the istio-k8s-operator
repository.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ._schema import IstioMetadataAppData

if TYPE_CHECKING:
    from ops import Application, CharmBase, RelationMapping

log = logging.getLogger(__name__)

DEFAULT_RELATION_NAME = 'istio-metadata'


class IstioMetadataRequirer:
    """Endpoint wrapper for the requirer side of the istio-metadata relation."""

    def __init__(
        self,
        relation_mapping: RelationMapping,
        relation_name: str = DEFAULT_RELATION_NAME,
    ) -> None:
        """Initialize the IstioMetadataRequirer object.

        This object is for accessing data from relations that use the istio_metadata
        interface.  It **does not** autonomously handle the events associated with
        that relation.  It is up to the charm using this object to observe those
        events as they see fit.  Typically, that charm should observe this
        relation's relation-changed event.

        This object is for interacting with a relation that has limit=1 set in
        charmcraft.yaml.  In particular, the get_data method will raise if more
        than one related application is available.

        Args:
            relation_mapping: The RelationMapping of a charm (typically
                              `self.model.relations` from within a charm object).
            relation_name: The name of the wrapped relation.
        """
        self._charm_relation_mapping = relation_mapping
        self._relation_name = relation_name

    @property
    def relations(self):
        """Return relation instances for applications related to us on the monitored relation."""
        return self._charm_relation_mapping.get(self._relation_name, ())

    def get_data(self) -> IstioMetadataAppData | None:
        """Return data for at most one related application, raising if more than one is available.

        Useful for charms that always expect exactly one related application.  It is
        recommended that those charms also set limit=1 for that relation in
        charmcraft.yaml.  Returns None if no data is available (either because no
        applications are related to us, or because the related application has not
        sent data).
        """
        relations = self.relations
        if len(relations) == 0:
            return None
        if len(relations) > 1:
            raise ValueError('Cannot get_info when more than one application is related.')

        # Being a little cautious here using getattr and get, since some funny things
        # have happened with relation data in the past.
        raw_data_dict = getattr(relations[0], 'data', {}).get(relations[0].app)
        if not raw_data_dict:
            return None

        return IstioMetadataAppData.model_validate(raw_data_dict)


class IstioMetadataProvider:
    """The provider side of the istio-metadata relation."""

    def __init__(
        self,
        charm: CharmBase,
        relation_mapping: RelationMapping,
        app: Application,
        relation_name: str = DEFAULT_RELATION_NAME,
    ):
        """Initialize the IstioMetadataProvider object.

        This object is for serializing and sending data to a relation that uses the
        istio_metadata interface - it does not automatically observe any events for
        that relation.  It is up to the charm using this to call publish when it is
        appropriate to do so, typically on at least the charm's leader_elected event
        and this relation's relation_joined event.

        Args:
            charm: The charm instantiating this object.
            relation_mapping: The RelationMapping of a charm (typically
                              `self.model.relations` from within a charm object).
            app: This application.
            relation_name: The name of the relation.
        """
        self._charm = charm
        self._charm_relation_mapping = relation_mapping
        self._app = app
        self._relation_name = relation_name

    @property
    def relations(self):
        """Return the applications related to us under the monitored relation."""
        return self._charm_relation_mapping.get(self._relation_name, ())

    def publish(self, root_namespace: str):
        """Post istio-metadata to all related applications.

        This method writes to the relation's app data bag, and thus should never be
        called by a unit that is not the leader otherwise ops will raise an exception.

        Args:
            root_namespace: The root namespace of the Istio deployment.
        """
        # Only the leader unit can update the application data bag
        if self._charm.unit.is_leader():
            data = IstioMetadataAppData(root_namespace=root_namespace).model_dump(
                mode='json', by_alias=True, exclude_defaults=True, round_trip=True
            )

            for relation in self.relations:
                databag = relation.data[self._app]
                databag.update(data)
