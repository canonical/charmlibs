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

"""Service mesh interface library.

This library facilitates adding your charmed application to a service mesh,
leveraging the ``service_mesh`` and ``cross_model_mesh`` interfaces to provide
secure, policy-driven traffic management between applications.

What is this library for?
=========================

This library is for enrolling a charm onto a Charmed Service Mesh solution
and automatically provisioning network policies that restrict cluster-internal
network traffic between charms.

Service meshes provide capabilities for routing, controlling, and monitoring
traffic between applications. A key feature is the ability to enforce
authorization policies that govern which pods can communicate with each other
and on which ports, paths, and HTTP methods. For example, you can define that
a metrics scraper pod is allowed to ``GET /metrics`` on port ``9090`` from a
producer pod, while preventing all other pods from accessing it.

The ``ServiceMeshConsumer`` subscribes a charm to a related service mesh by
declaring access policies based on the charm's Juju relations. Since
application relations often reflect traffic flow patterns (e.g. a database
consumer connecting to a database provider), the consumer automatically
generates the appropriate mesh traffic rules. It also handles labelling the
charm's Kubernetes resources to enroll them in the mesh, and supports
cross-model relations for multi-model deployments.

The ``ServiceMeshProvider`` publishes mesh enrollment labels and the mesh type
to consumers, and collects the aggregated policies requested by all related
consumer charms so the mesh control plane can enforce them.

Consumer usage::

    from charmlibs.interfaces.service_mesh import (
        Method, Endpoint, AppPolicy, UnitPolicy, ServiceMeshConsumer,
    )

    class MyCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self._mesh = ServiceMeshConsumer(
                self,
                policies=[
                    AppPolicy(
                        relation="data",
                        endpoints=[
                            Endpoint(
                                ports=[HTTP_LISTEN_PORT],
                                methods=[Method.get],
                                paths=["/data"],
                            ),
                        ],
                    ),
                    UnitPolicy(relation="metrics", ports=[HTTP_LISTEN_PORT]),
                ],
            )

Provider usage::

    from charmlibs.interfaces.service_mesh import ServiceMeshProvider, MeshType

    class MyServiceMeshCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self._mesh = ServiceMeshProvider(
                charm=self,
                labels={"istio.io/dataplane-mode": "ambient"},
                mesh_type=MeshType.istio,
            )
"""

from canonical_service_mesh.enums import MeshType, Method, PolicyTargetType

from ._service_mesh import (
    AppPolicy,
    CMRData,
    Endpoint,
    MeshPolicy,
    Policy,
    ServiceMeshConsumer,
    ServiceMeshProvider,
    ServiceMeshProviderAppData,
    UnitPolicy,
    build_mesh_policies,
    get_data_from_cmr_relation,
    label_configmap_name_template,
)
from ._version import __version__ as __version__

__all__ = [
    'AppPolicy',
    'CMRData',
    'Endpoint',
    'MeshPolicy',
    'MeshType',
    'Method',
    'Policy',
    'PolicyTargetType',
    'ServiceMeshConsumer',
    'ServiceMeshProvider',
    'ServiceMeshProviderAppData',
    'UnitPolicy',
    'build_mesh_policies',
    'get_data_from_cmr_relation',
    'label_configmap_name_template',
]
