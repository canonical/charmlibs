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
relation interface. The provider charm publishes metadata about its Gateway workload
(namespace, gateway name, deployment name, service account) and the requirer charm
reads it.

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
