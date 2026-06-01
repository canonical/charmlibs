# Copyright 2024 Canonical Ltd.
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

"""Service mesh interface implementation."""

import json
import logging
import warnings
from typing import TYPE_CHECKING, Any

import pydantic
from canonical_service_mesh.enums import MeshType, Method, PolicyTargetType
from canonical_service_mesh.utils.istio import (
    label_configmap_name_template,
    reconcile_charm_labels,
)
from ops import CharmBase, Object, RelationMapping
from ops.charm import RelationEvent
from ops.framework import EventBase
from pydantic import Field

if TYPE_CHECKING:
    from lightkube import Client
    from ops.model import Relation

logger = logging.getLogger(__name__)


class Endpoint(pydantic.BaseModel):
    """Data type for a policy endpoint."""

    hosts: list[str] | None = None
    ports: list[int] | None = None
    methods: list[Method] | None = None
    paths: list[str] | None = None


class Policy(pydantic.BaseModel):
    """Data type for defining a policy for your charm.

    .. deprecated::
        Use ``AppPolicy`` for fine-grained application-level policies
        or ``UnitPolicy`` to allow access to charm units.
    """

    relation: str
    endpoints: list[Endpoint]
    service: str | None = None

    def __init__(self, **data: Any):
        warnings.warn(
            'Policy is deprecated. Use AppPolicy for fine-grained application-level policies '
            'or UnitPolicy to allow access to charm units. For migration, Policy can be '
            'directly replaced with AppPolicy.',
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(**data)


class AppPolicy(pydantic.BaseModel):
    """Data type for defining a policy for your charm application."""

    relation: str
    endpoints: list[Endpoint]
    service: str | None = None


class UnitPolicy(pydantic.BaseModel):
    """Data type for defining a policy for your charm unit."""

    relation: str
    ports: list[int] | None = None


class MeshPolicy(pydantic.BaseModel):
    """A generic MeshPolicy data type that describes mesh policies.

    This is agnostic to the mesh type and defines a standard interface for charmed
    mesh managed policies.
    """

    source_namespace: str
    source_app_name: str
    target_namespace: str
    target_app_name: str | None = None
    target_selector_labels: dict[str, str] | None = None
    target_service: str | None = None
    target_type: PolicyTargetType = PolicyTargetType.app
    endpoints: list[Endpoint] = Field(default_factory=lambda: list[Endpoint]())

    @pydantic.model_validator(mode='after')
    def _validate(self):
        """Validate cross field constraints for the mesh policy."""
        if self.target_type == PolicyTargetType.app:
            self._validate_app_policy()
        elif self.target_type == PolicyTargetType.unit:
            self._validate_unit_policy()
        return self

    def _validate_app_policy(self) -> None:
        """Validate app-targeted policy constraints."""
        if not any([self.target_app_name, self.target_service]):
            raise ValueError(
                f'Bad policy configuration. Neither target_app_name nor target_service '
                f'specified for MeshPolicy with target_type {self.target_type}'
            )
        if self.target_selector_labels:
            raise ValueError(
                f'Bad policy configuration. MeshPolicy with target_type {self.target_type} '
                f'does not support target_selector_labels.'
            )

    def _validate_unit_policy(self) -> None:
        """Validate unit-targeted policy constraints."""
        if self.target_app_name and self.target_selector_labels:
            raise ValueError(
                f'Bad policy configuration. MeshPolicy with target_type {self.target_type} '
                f'cannot specify both target_app_name and target_selector_labels.'
            )
        if self.target_service:
            raise ValueError(
                f'Bad policy configuration. MeshPolicy with target_type {self.target_type} '
                f'does not support target_service.'
            )


class ServiceMeshProviderAppData(pydantic.BaseModel):
    """Data provided by the provider side of the service-mesh interface."""

    labels: dict[str, str]
    mesh_type: MeshType


class CMRData(pydantic.BaseModel):
    """Data type containing the info required for cross-model relations."""

    app_name: str
    juju_model_name: str


class ServiceMeshConsumer(Object):
    """Class used for joining a service mesh."""

    def __init__(
        self,
        charm: CharmBase,
        mesh_relation_name: str = 'service-mesh',
        cross_model_mesh_requires_name: str = 'require-cmr-mesh',
        cross_model_mesh_provides_name: str = 'provide-cmr-mesh',
        policies: list[Policy | AppPolicy | UnitPolicy] | None = None,
        auto_join: bool = True,
    ):
        """Class used for joining a service mesh.

        Args:
            charm: The charm instantiating this object.
            mesh_relation_name: The relation name for the service_mesh interface.
            cross_model_mesh_requires_name: The relation name for the cross_model_mesh
                requirer interface.
            cross_model_mesh_provides_name: The relation name for the cross_model_mesh
                provider interface.
            policies: List of access policies this charm supports.
            auto_join: Automatically join the mesh by applying labels to charm pods.
        """
        super().__init__(charm, mesh_relation_name)
        self._charm = charm
        self._relation = self._charm.model.get_relation(mesh_relation_name)
        self._cmr_relations = self._charm.model.relations[cross_model_mesh_provides_name]
        self._policies = policies or []
        self._label_configmap_name = label_configmap_name_template.format(
            app_name=self._charm.app.name
        )
        self._lightkube_client: Client | None = None
        if auto_join:
            self.framework.observe(
                self._charm.on[mesh_relation_name].relation_changed, self._update_labels
            )
            self.framework.observe(
                self._charm.on[mesh_relation_name].relation_broken, self._on_mesh_broken
            )
        self.framework.observe(
            self._charm.on[mesh_relation_name].relation_created, self._relations_changed
        )
        self.framework.observe(
            self._charm.on[cross_model_mesh_requires_name].relation_created, self._send_cmr_data
        )
        self.framework.observe(
            self._charm.on[cross_model_mesh_provides_name].relation_changed,
            self._relations_changed,
        )
        self.framework.observe(self._charm.on.upgrade_charm, self._relations_changed)
        relations = {policy.relation for policy in self._policies}
        for relation in relations:
            self.framework.observe(
                self._charm.on[relation].relation_created, self._relations_changed
            )
            self.framework.observe(
                self._charm.on[relation].relation_broken, self._relations_changed
            )

    def _send_cmr_data(self, event: RelationEvent) -> None:
        """Send app and model information for CMR."""
        if not self._charm.unit.is_leader():
            return
        data = CMRData(
            app_name=self._charm.app.name, juju_model_name=self._charm.model.name
        ).model_dump()
        event.relation.data[self._charm.app]['cmr_data'] = json.dumps(data)

    def _relations_changed(self, _event: EventBase) -> None:
        if not self._charm.unit.is_leader():
            return
        self.update_service_mesh()

    def update_service_mesh(self):
        """Update the service mesh.

        Gathers information from all relations of the charm and updates the mesh appropriately to
        allow communication.
        """
        if self._relation is None:
            return
        logger.debug('Updating service mesh policies.')

        cmr_application_data = get_data_from_cmr_relation(self._cmr_relations)

        mesh_policies = build_mesh_policies(
            relation_mapping=self._charm.model.relations,
            target_app_name=self._charm.app.name,
            target_namespace=self._my_namespace(),
            policies=self._policies,
            cmr_application_data=cmr_application_data,
        )
        self._relation.data[self._charm.app]['policies'] = json.dumps([
            p.model_dump() for p in mesh_policies
        ])

    def _my_namespace(self) -> str:
        """Return the namespace of the running charm."""
        return self._charm.model.name

    def _get_app_data(self) -> ServiceMeshProviderAppData | None:
        """Return the relation data for the remote application."""
        if self._relation is None or not self._relation.app:
            return None

        raw_data = self._relation.data[self._relation.app]
        if len(raw_data) == 0:
            return None

        raw_data = {k: json.loads(v) for k, v in raw_data.items()}
        return ServiceMeshProviderAppData.model_validate(raw_data)

    def labels(self) -> dict[str, str]:
        """Labels required for a pod to join the mesh."""
        app_data = self._get_app_data()
        if app_data is None:
            return {}
        return app_data.labels

    @property
    def enabled(self) -> bool:
        """Return if the consumer is currently in the mesh."""
        if self._relation is None or not self._relation.app:
            return False
        return True

    def mesh_type(self) -> MeshType | None:
        """Return the type of the service mesh."""
        app_data = self._get_app_data()
        if app_data is None:
            return None
        return app_data.mesh_type

    def _on_mesh_broken(self, _event: EventBase) -> None:
        if not self._charm.unit.is_leader():
            return
        self._set_labels({})
        self._delete_label_configmap()

    def _update_labels(self, _event: EventBase) -> None:
        self._set_labels(self.labels())

    def _set_labels(self, labels: dict[str, str]) -> None:
        """Add labels to the charm's Pods (via StatefulSet) and Service."""
        reconcile_charm_labels(
            client=self.lightkube_client,
            app_name=self._charm.app.name,
            namespace=self._charm.model.name,
            label_configmap_name=self._label_configmap_name,
            labels=labels,
        )

    def _delete_label_configmap(self) -> None:
        from lightkube.resources.core_v1 import ConfigMap

        client = self.lightkube_client
        client.delete(res=ConfigMap, name=self._label_configmap_name)

    @property
    def lightkube_client(self) -> 'Client':
        """Returns a lightkube client configured for this library."""
        if self._lightkube_client is None:
            from lightkube import Client

            self._lightkube_client = Client(
                namespace=self._charm.model.name, field_manager=self._charm.app.name
            )
        return self._lightkube_client


class ServiceMeshProvider(Object):
    """Provide a service mesh to applications."""

    def __init__(
        self,
        charm: CharmBase,
        labels: dict[str, str],
        mesh_type: MeshType,
        mesh_relation_name: str = 'service-mesh',
    ):
        """Class used to provide information needed to join the service mesh.

        Args:
            charm: The charm instantiating this object.
            labels: The labels which related applications need to apply to use the mesh.
            mesh_type: The type of this service mesh.
            mesh_relation_name: The relation name for the service_mesh interface.
        """
        super().__init__(charm, mesh_relation_name)
        self._charm = charm
        self._relation_name = mesh_relation_name
        self._labels = labels
        self._mesh_type = mesh_type
        self.framework.observe(
            self._charm.on[mesh_relation_name].relation_created, self._relation_created
        )
        self.framework.observe(self._charm.on.config_changed, self._on_config_changed)

    def _relation_created(self, _event: EventBase) -> None:
        self.update_relations()

    def _on_config_changed(self, _event: EventBase) -> None:
        self.update_relations()

    def update_relations(self):
        """Update all relations with the labels needed to use the mesh."""
        if self._charm.unit.is_leader():
            data = ServiceMeshProviderAppData(
                labels=self._labels,
                mesh_type=self._mesh_type,
            ).model_dump(mode='json', by_alias=True, exclude_defaults=True, round_trip=True)
            data = {k: json.dumps(v) for k, v in data.items()}
            for relation in self._charm.model.relations[self._relation_name]:
                relation.data[self._charm.app].update(data)

    def mesh_info(self) -> list[MeshPolicy]:
        """Return the relation data that defines Policies requested by the related applications."""
        mesh_info: list[MeshPolicy] = []
        for relation in self._charm.model.relations[self._relation_name]:
            policies_data = json.loads(relation.data[relation.app].get('policies', '[]'))
            policies = [MeshPolicy.model_validate(policy) for policy in policies_data]
            mesh_info.extend(policies)
        return mesh_info


def build_mesh_policies(
    relation_mapping: RelationMapping,
    target_app_name: str,
    target_namespace: str,
    policies: list[Policy | AppPolicy | UnitPolicy],
    cmr_application_data: dict[str, CMRData] | None = None,
) -> list[MeshPolicy]:
    """Generate MeshPolicy objects for the currently related applications.

    Args:
        relation_mapping: Charm's RelationMapping object, for example self.model.relations.
        target_app_name: The name of the target application, for example self.app.name.
        target_namespace: The namespace of the target application, for example self.model.name.
        policies: List of AppPolicy, or UnitPolicy objects defining the access rules.
        cmr_application_data: Data for cross-model relations, mapping app names to CMRData.
    """
    if not cmr_application_data:
        cmr_application_data = {}

    mesh_policies: list[MeshPolicy] = []
    for policy in policies:
        logger.debug("Processing policy for relation endpoint '%s'.", policy.relation)
        for relation in relation_mapping[policy.relation]:
            logger.debug("Processing policy for related application '%s'.", relation.app.name)
            if relation.app.name in cmr_application_data:
                logger.debug('Found cross model relation: %s. Creating policy.', relation.name)
                source_app_name = cmr_application_data[relation.app.name].app_name
                source_namespace = cmr_application_data[relation.app.name].juju_model_name
            else:
                logger.debug('Found in-model relation: %s. Creating policy.', relation.name)
                source_app_name = relation.app.name
                source_namespace = target_namespace

            if isinstance(policy, UnitPolicy):
                mesh_policies.append(
                    MeshPolicy(
                        source_namespace=source_namespace,
                        source_app_name=source_app_name,
                        target_namespace=target_namespace,
                        target_app_name=target_app_name,
                        target_service=None,
                        target_type=PolicyTargetType.unit,
                        endpoints=[Endpoint(ports=policy.ports)] if policy.ports else [],
                    )
                )
            else:
                mesh_policies.append(
                    MeshPolicy(
                        source_namespace=source_namespace,
                        source_app_name=source_app_name,
                        target_namespace=target_namespace,
                        target_app_name=target_app_name,
                        target_service=policy.service,
                        target_type=PolicyTargetType.app,
                        endpoints=policy.endpoints,
                    )
                )

    return mesh_policies


def get_data_from_cmr_relation(
    cmr_relations: list['Relation'],
) -> dict[str, CMRData]:
    """Return a dictionary of CMRData from the established cross-model relations."""
    cmr_data: dict[str, CMRData] = {}
    for cmr in cmr_relations:
        if 'cmr_data' in cmr.data[cmr.app]:
            try:
                cmr_data[cmr.app.name] = CMRData.model_validate(
                    json.loads(cmr.data[cmr.app]['cmr_data'])
                )
            except pydantic.ValidationError:
                logger.exception('Invalid CMR data for %s', cmr.app.name)
                continue
    return cmr_data
