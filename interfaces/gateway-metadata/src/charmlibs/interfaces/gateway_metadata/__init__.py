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

"""Gateway metadata interface library.

This library provides the provider and requirer sides of the ``gateway-metadata``
relation interface for sharing Kubernetes Gateway API metadata (name, namespace,
deployment name, service account) between gateway providers and consuming charms.

What is this library for?
=========================

Charms that wrap a Kubernetes Gateway API resource (e.g. ``istio-ingress-k8s``)
automatically spin up a Gateway resource which creates proxy pods and routes for
traffic routing. In certain cases, charms using the gateway need to know specific
information about the gateway itself, including the gateway name, gateway class,
and other details. This information can be used to create custom resources that
attach to the gateway.

The ``gateway-metadata`` interface provides an umbrella relation containing gateway
information that requiring charms can use to attach custom resources to the gateway
managed by the provider charm. While currently used by the ``istio-ingress-k8s``
charm, it is designed for any charm that wraps a Kubernetes Gateway API resource.

Provider usage::

    from charmlibs.interfaces.gateway_metadata import GatewayMetadata, GatewayMetadataProvider

    class MyGatewayCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.gateway_metadata = GatewayMetadataProvider(self)

        def _publish(self):
            self.gateway_metadata.publish_metadata(
                GatewayMetadata(
                    namespace="istio-system",
                    gateway_name="my-gateway",
                    deployment_name="my-gateway",
                    service_account="my-gateway",
                )
            )

Requirer usage::

    from charmlibs.interfaces.gateway_metadata import GatewayMetadataRequirer

    class MyConsumerCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.gateway_metadata = GatewayMetadataRequirer(self)

        def _read(self):
            if self.gateway_metadata.is_ready:
                metadata = self.gateway_metadata.get_metadata()
"""

from ._gateway_metadata import (
    GatewayMetadata,
    GatewayMetadataProvider,
    GatewayMetadataRequirer,
)
from ._version import __version__ as __version__

__all__ = [
    'GatewayMetadata',
    'GatewayMetadataProvider',
    'GatewayMetadataRequirer',
]
