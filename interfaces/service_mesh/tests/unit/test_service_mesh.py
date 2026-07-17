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

"""Unit tests for the service-mesh interface library."""

from __future__ import annotations

import json
from typing import Any

import ops
import pytest
import scenario
from pydantic import ValidationError

from charmlibs.interfaces.service_mesh import (
    AppPolicy,
    CMRData,
    Endpoint,
    MeshPolicy,
    MeshType,
    Method,
    Policy,
    PolicyTargetType,
    ServiceMeshConsumer,
    ServiceMeshProvider,
    ServiceMeshProviderAppData,
    UnitPolicy,
    build_mesh_policies,
)

MESH_RELATION = 'service-mesh'
MESH_INTERFACE = 'service_mesh'
MESH_LABELS = {'istio.io/dataplane-mode': 'ambient'}

ENDPOINT_A = Endpoint(hosts=[], ports=[80], methods=[], paths=[])


class ConsumerCharm(ops.CharmBase):
    """Charm used in consumer tests."""

    mesh: ServiceMeshConsumer


class ProviderCharm(ops.CharmBase):
    """Charm used in provider tests."""

    mesh: ServiceMeshProvider


def consumer_context(
    policies: list[Policy | AppPolicy | UnitPolicy],
) -> scenario.Context[ConsumerCharm]:
    meta = {
        'name': 'consumer-charm',
        'requires': {
            'service-mesh': {'interface': 'service_mesh'},
            'require-cmr-mesh': {'interface': 'cross_model_mesh'},
            'rela': {'interface': 'foo'},
            'relb': {'interface': 'foo'},
        },
        'provides': {
            'provide-cmr-mesh': {'interface': 'cross_model_mesh'},
            'relc': {'interface': 'foo'},
            'reld': {'interface': 'foo'},
        },
    }

    class _ConsumerCharm(ConsumerCharm):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.mesh = ServiceMeshConsumer(charm=self, policies=policies, auto_join=False)

    return scenario.Context(_ConsumerCharm, meta)


def provider_context() -> scenario.Context[ProviderCharm]:
    meta = {
        'name': 'provider-charm',
        'provides': {MESH_RELATION: {'interface': MESH_INTERFACE}},
    }

    class _ProviderCharm(ProviderCharm):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.mesh = ServiceMeshProvider(
                self,
                labels=MESH_LABELS,
                mesh_relation_name=MESH_RELATION,
                mesh_type=MeshType.istio,
            )

    return scenario.Context(_ProviderCharm, meta)


@pytest.mark.parametrize(
    'policy_data, should_raise, error_message',
    [
        (
            {
                'source_app_name': 'source-app',
                'source_namespace': 'source-ns',
                'target_namespace': 'target-ns',
                'target_app_name': 'target-app',
                'target_type': PolicyTargetType.app,
                'endpoints': [Endpoint(ports=[80])],
            },
            False,
            None,
        ),
        (
            {
                'source_app_name': 'source-app',
                'source_namespace': 'source-ns',
                'target_namespace': 'target-ns',
                'target_service': 'my-service',
                'target_type': PolicyTargetType.app,
                'endpoints': [Endpoint(ports=[80])],
            },
            False,
            None,
        ),
        (
            {
                'source_app_name': 'source-app',
                'source_namespace': 'source-ns',
                'target_namespace': 'target-ns',
                'target_type': PolicyTargetType.app,
                'endpoints': [Endpoint(ports=[80])],
            },
            True,
            'Neither target_app_name nor target_service specified'
            f' for MeshPolicy with target_type {PolicyTargetType.app}',
        ),
        (
            {
                'source_app_name': 'source-app',
                'source_namespace': 'source-ns',
                'target_namespace': 'target-ns',
                'target_app_name': 'target-app',
                'target_selector_labels': {'app': 'my-app'},
                'target_type': PolicyTargetType.app,
                'endpoints': [Endpoint(ports=[80])],
            },
            True,
            f'MeshPolicy with target_type {PolicyTargetType.app}'
            ' does not support target_selector_labels.',
        ),
        (
            {
                'source_app_name': 'source-app',
                'source_namespace': 'source-ns',
                'target_namespace': 'target-ns',
                'target_app_name': 'target-app',
                'target_type': PolicyTargetType.unit,
                'endpoints': [Endpoint(ports=[8080])],
            },
            False,
            None,
        ),
        (
            {
                'source_app_name': 'source-app',
                'source_namespace': 'source-ns',
                'target_namespace': 'target-ns',
                'target_selector_labels': {'app': 'my-app'},
                'target_type': PolicyTargetType.unit,
                'endpoints': [Endpoint(ports=[8080])],
            },
            False,
            None,
        ),
        (
            {
                'source_app_name': 'source-app',
                'source_namespace': 'source-ns',
                'target_namespace': 'target-ns',
                'target_app_name': 'target-app',
                'target_selector_labels': {'app': 'my-app'},
                'target_type': PolicyTargetType.unit,
                'endpoints': [Endpoint(ports=[8080])],
            },
            True,
            f'MeshPolicy with target_type {PolicyTargetType.unit}'
            ' cannot specify both target_app_name and target_selector_labels.',
        ),
    ],
)
def test_mesh_policy_validation(
    policy_data: dict[str, Any], should_raise: bool, error_message: str | None
) -> None:
    """Test MeshPolicy pydantic validations for various configurations."""
    if should_raise:
        with pytest.raises(ValidationError) as exc_info:
            MeshPolicy(**policy_data)
        assert error_message is not None
        assert error_message in str(exc_info.value)
    else:
        policy = MeshPolicy(**policy_data)
        assert policy.source_app_name == 'source-app'


def test_mesh_policy_roundtrip() -> None:
    policy = MeshPolicy(
        source_namespace='ns1',
        source_app_name='app1',
        target_namespace='ns2',
        target_app_name='app2',
        target_type=PolicyTargetType.app,
        endpoints=[Endpoint(ports=[80], methods=[Method.get], paths=['/api'])],
    )
    dumped = json.dumps(policy.model_dump())
    restored = MeshPolicy.model_validate(json.loads(dumped))
    assert restored == policy


def test_endpoint_defaults() -> None:
    ep = Endpoint()
    assert ep.hosts is None
    assert ep.ports is None
    assert ep.methods is None
    assert ep.paths is None


def test_cmr_data_roundtrip() -> None:
    data = CMRData(app_name='remote', juju_model_name='model-a')
    dumped = json.dumps(data.model_dump())
    restored = CMRData.model_validate(json.loads(dumped))
    assert restored == data


def test_provider_sends_data() -> None:
    ctx = provider_context()
    mesh_relation = scenario.Relation(endpoint=MESH_RELATION, interface=MESH_INTERFACE)
    state = scenario.State(relations=[mesh_relation], leader=True)
    out = ctx.run(ctx.on.relation_created(mesh_relation), state)
    raw_data = {
        k: json.loads(v) for k, v in out.get_relation(mesh_relation.id).local_app_data.items()
    }
    actual = ServiceMeshProviderAppData.model_validate(raw_data)
    assert actual.labels == MESH_LABELS
    assert actual.mesh_type == MeshType.istio


EXAMPLE_MESH_POLICY_1 = MeshPolicy(
    source_namespace='namespace1-1',
    source_app_name='app1-1',
    target_namespace='namespace2-1',
    target_app_name='app2-1',
    target_type=PolicyTargetType.app,
    endpoints=[],
)

EXAMPLE_MESH_POLICY_2 = MeshPolicy(
    source_namespace='namespace1-2',
    source_app_name='app-2',
    target_namespace='namespace-2',
    target_app_name='app-2',
    target_type=PolicyTargetType.app,
    endpoints=[],
)

EXAMPLE_MESH_POLICY_3 = MeshPolicy(
    source_namespace='namespace1-3',
    source_app_name='app1-3',
    target_namespace='namespace2-3',
    target_app_name='app2-3',
    target_type=PolicyTargetType.app,
    endpoints=[],
)


@pytest.mark.parametrize(
    'mesh_relations, expected_data',
    [
        (
            [
                scenario.Relation(
                    endpoint=MESH_RELATION,
                    interface=MESH_INTERFACE,
                    remote_app_data={
                        'policies': json.dumps([
                            EXAMPLE_MESH_POLICY_1.model_dump(mode='json'),
                            EXAMPLE_MESH_POLICY_2.model_dump(mode='json'),
                        ]),
                    },
                ),
                scenario.Relation(
                    endpoint=MESH_RELATION,
                    interface=MESH_INTERFACE,
                    remote_app_data={
                        'policies': json.dumps([
                            EXAMPLE_MESH_POLICY_3.model_dump(mode='json'),
                        ]),
                    },
                ),
            ],
            [EXAMPLE_MESH_POLICY_1, EXAMPLE_MESH_POLICY_2, EXAMPLE_MESH_POLICY_3],
        ),
        (
            [
                scenario.Relation(
                    endpoint=MESH_RELATION,
                    interface=MESH_INTERFACE,
                    remote_app_data={
                        'policies': json.dumps([
                            EXAMPLE_MESH_POLICY_1.model_dump(mode='json'),
                            EXAMPLE_MESH_POLICY_2.model_dump(mode='json'),
                        ]),
                    },
                ),
                scenario.Relation(
                    endpoint=MESH_RELATION,
                    interface=MESH_INTERFACE,
                    remote_app_data={'policies': json.dumps([])},
                ),
            ],
            [EXAMPLE_MESH_POLICY_1, EXAMPLE_MESH_POLICY_2],
        ),
        (
            [
                scenario.Relation(
                    endpoint=MESH_RELATION,
                    interface=MESH_INTERFACE,
                    remote_app_data={
                        'policies': json.dumps([
                            EXAMPLE_MESH_POLICY_1.model_dump(mode='json'),
                            EXAMPLE_MESH_POLICY_2.model_dump(mode='json'),
                        ]),
                    },
                ),
                scenario.Relation(
                    endpoint=MESH_RELATION,
                    interface=MESH_INTERFACE,
                    remote_app_data={},
                ),
            ],
            [EXAMPLE_MESH_POLICY_1, EXAMPLE_MESH_POLICY_2],
        ),
    ],
)
def test_provider_reads_data(
    mesh_relations: list[scenario.Relation], expected_data: list[MeshPolicy]
) -> None:
    ctx = provider_context()
    state = scenario.State(relations=mesh_relations)
    with ctx(ctx.on.update_status(), state=state) as manager:
        actual_mesh_policies = manager.charm.mesh.mesh_info()
        assert actual_mesh_policies == expected_data


WITH_COMPLEX_ENDPOINTS = (
    [
        AppPolicy(
            relation='rela',
            endpoints=[
                Endpoint(
                    hosts=['localhost'],
                    ports=[443, 9000],
                    methods=['GET', 'POST'],  # type: ignore
                    paths=['/metrics', '/data'],
                ),
                Endpoint(
                    hosts=['example.com'],
                    ports=[3000],
                    methods=['DELETE'],  # type: ignore
                    paths=['/foobar'],
                ),
            ],
            service=None,
        )
    ],
    [
        {
            'source_app_name': 'remote_a',
            'source_namespace': 'my_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [
                {
                    'hosts': ['localhost'],
                    'ports': [443, 9000],
                    'methods': ['GET', 'POST'],
                    'paths': ['/metrics', '/data'],
                },
                {
                    'hosts': ['example.com'],
                    'ports': [3000],
                    'methods': ['DELETE'],
                    'paths': ['/foobar'],
                },
            ],
        }
    ],
)

MULTIPLE_POLICIES = (
    [
        AppPolicy(relation='rela', endpoints=[ENDPOINT_A], service=None),
        AppPolicy(relation='relc', endpoints=[ENDPOINT_A], service=None),
    ],
    [
        {
            'source_app_name': 'remote_a',
            'source_namespace': 'my_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [{'hosts': [], 'ports': [80], 'methods': [], 'paths': []}],
        },
        {
            'source_app_name': 'remote_c',
            'source_namespace': 'my_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [{'hosts': [], 'ports': [80], 'methods': [], 'paths': []}],
        },
    ],
)

REQUIRER = (
    [AppPolicy(relation='rela', endpoints=[ENDPOINT_A], service=None)],
    [
        {
            'source_app_name': 'remote_a',
            'source_namespace': 'my_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [{'hosts': [], 'ports': [80], 'methods': [], 'paths': []}],
        }
    ],
)

REQUIRER_CMR = (
    [AppPolicy(relation='relb', endpoints=[ENDPOINT_A], service=None)],
    [
        {
            'source_app_name': 'remote_b',
            'source_namespace': 'remote_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [{'hosts': [], 'ports': [80], 'methods': [], 'paths': []}],
        }
    ],
)

PROVIDER = (
    [AppPolicy(relation='relc', endpoints=[ENDPOINT_A], service=None)],
    [
        {
            'source_app_name': 'remote_c',
            'source_namespace': 'my_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [{'hosts': [], 'ports': [80], 'methods': [], 'paths': []}],
        }
    ],
)

PROVIDER_CMR = (
    [AppPolicy(relation='reld', endpoints=[ENDPOINT_A], service=None)],
    [
        {
            'source_app_name': 'remote_d',
            'source_namespace': 'remote_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [{'hosts': [], 'ports': [80], 'methods': [], 'paths': []}],
        }
    ],
)

POLICY_DEPRECATED = (
    [Policy(relation='rela', endpoints=[ENDPOINT_A], service=None)],
    [
        {
            'source_app_name': 'remote_a',
            'source_namespace': 'my_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'app',
            'endpoints': [{'hosts': [], 'ports': [80], 'methods': [], 'paths': []}],
        }
    ],
)

UNIT_POLICY = (
    [UnitPolicy(relation='rela', ports=[8080])],
    [
        {
            'source_app_name': 'remote_a',
            'source_namespace': 'my_model',
            'target_app_name': 'consumer-charm',
            'target_namespace': 'my_model',
            'target_selector_labels': None,
            'target_service': None,
            'target_type': 'unit',
            'endpoints': [{'hosts': None, 'ports': [8080], 'methods': None, 'paths': None}],
        }
    ],
)


@pytest.mark.parametrize(
    'policies,expected_data',
    [
        WITH_COMPLEX_ENDPOINTS,
        MULTIPLE_POLICIES,
        REQUIRER,
        REQUIRER_CMR,
        PROVIDER,
        PROVIDER_CMR,
        POLICY_DEPRECATED,
        UNIT_POLICY,
    ],
)
def test_relation_data_policies(
    policies: list[Policy | AppPolicy | UnitPolicy], expected_data: list[dict[str, Any]]
) -> None:
    """Test that a given list of policies produces the expected output.

    Sets up 4 relations: requirer, requirer_cmr, provider, and provider_cmr. The
    policies can be on any combination of these relations and should produce
    proper objects.
    """
    ctx = consumer_context(policies)
    mesh_relation = scenario.Relation(endpoint='service-mesh', interface='service_mesh')
    rela = scenario.Relation('rela', 'foo', remote_app_name='remote_a')
    relb = scenario.Relation('relb', 'foo', remote_app_name='masked_name_b')
    cmr_relb = scenario.Relation(
        'provide-cmr-mesh',
        'cross_model_mesh',
        remote_app_name='masked_name_b',
        remote_app_data={
            'cmr_data': json.dumps({'app_name': 'remote_b', 'juju_model_name': 'remote_model'})
        },
    )
    relc = scenario.Relation('relc', 'foo', remote_app_name='remote_c')
    reld = scenario.Relation('reld', 'foo', remote_app_name='masked_name_d')
    cmr_reld = scenario.Relation(
        'provide-cmr-mesh',
        'cross_model_mesh',
        remote_app_name='masked_name_d',
        remote_app_data={
            'cmr_data': json.dumps({'app_name': 'remote_d', 'juju_model_name': 'remote_model'})
        },
    )
    state = scenario.State(
        relations={mesh_relation, rela, relb, cmr_relb, relc, reld, cmr_reld},
        leader=True,
        model=scenario.Model(name='my_model'),
    )
    out = ctx.run(ctx.on.relation_created(relation=mesh_relation), state)
    assert (
        json.loads(out.get_relation(mesh_relation.id).local_app_data['policies']) == expected_data
    )


def test_getting_relation_data() -> None:
    """Test that the consumer can read relation data set by a provider."""
    ctx = consumer_context([AppPolicy(relation='rela', endpoints=[ENDPOINT_A], service=None)])
    labels_actual = {'label1': 'value1', 'label2': 'value2'}
    mesh_type_actual = MeshType.istio
    expected_data = ServiceMeshProviderAppData(
        labels=labels_actual,
        mesh_type=mesh_type_actual,
    )
    mesh_relation = scenario.Relation(
        endpoint='service-mesh',
        interface='service_mesh',
        remote_app_data={
            'labels': json.dumps(labels_actual),
            'mesh_type': json.dumps(mesh_type_actual),
        },
    )
    state = scenario.State(relations={mesh_relation}, leader=True)
    with ctx(ctx.on.relation_changed(relation=mesh_relation), state) as manager:
        assert labels_actual == manager.charm.mesh.labels()
        assert mesh_type_actual == manager.charm.mesh.mesh_type()
        assert expected_data == manager.charm.mesh._get_app_data()
        assert manager.charm.mesh.enabled is True


def test_enabled_true_when_relation_exists() -> None:
    """Test that enabled returns True when the mesh relation exists, even without data."""
    ctx = consumer_context([AppPolicy(relation='rela', endpoints=[ENDPOINT_A], service=None)])
    mesh_relation = scenario.Relation(endpoint='service-mesh', interface='service_mesh')
    state = scenario.State(relations={mesh_relation}, leader=True)
    with ctx(ctx.on.relation_changed(relation=mesh_relation), state) as manager:
        assert manager.charm.mesh.enabled is True


def test_enabled_false_when_no_relation() -> None:
    """Test that enabled returns False when there is no mesh relation."""
    ctx = consumer_context([AppPolicy(relation='rela', endpoints=[ENDPOINT_A], service=None)])
    state = scenario.State(relations=set(), leader=True)
    with ctx(ctx.on.start(), state) as manager:
        assert manager.charm.mesh.enabled is False


def test_enabled_false_after_relation_broken() -> None:
    """Test that enabled returns False after the mesh relation is broken."""
    ctx = consumer_context([AppPolicy(relation='rela', endpoints=[ENDPOINT_A], service=None)])
    mesh_relation = scenario.Relation(endpoint='service-mesh', interface='service_mesh')
    state = scenario.State(relations={mesh_relation}, leader=True)
    with ctx(ctx.on.relation_broken(relation=mesh_relation), state) as manager:
        assert manager.charm.mesh.enabled is False


def test_build_mesh_policies_empty() -> None:
    result = build_mesh_policies(
        relation_mapping={},  # type: ignore[arg-type]
        target_app_name='my-app',
        target_namespace='my-ns',
        policies=[],
    )
    assert result == []
