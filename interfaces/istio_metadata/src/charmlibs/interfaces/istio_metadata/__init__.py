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

"""Istio metadata interface library.

This library provides the provider and requirer sides of the ``istio_metadata``
relation interface, used to transfer information about an instance of Istio
(such as its root namespace) to charms that need to interface with Istio.

Provider usage::

    from charmlibs.interfaces.istio_metadata import IstioMetadataProvider

    class FooCharm(CharmBase):
        def __init__(self, framework):
            super().__init__(framework)
            self.istio_metadata = IstioMetadataProvider(
                charm=self,
                relation_mapping=self.model.relations,
                app=self.app,
            )

            self.framework.observe(self.on.leader_elected, self._publish)
            self.framework.observe(
                self.on['istio-metadata'].relation_joined, self._publish
            )

        def _publish(self, _):
            self.istio_metadata.publish(root_namespace='istio-system')

The provider's ``charmcraft.yaml`` should declare::

    provides:
      istio-metadata:
        interface: istio_metadata

Requirer usage::

    from charmlibs.interfaces.istio_metadata import IstioMetadataRequirer

    class FooCharm(CharmBase):
        def __init__(self, framework):
            super().__init__(framework)
            self.istio_metadata = IstioMetadataRequirer(
                self.model.relations, 'istio-metadata',
            )

            self.framework.observe(
                self.on['istio-metadata'].relation_changed, self._on_changed
            )
            self.framework.observe(
                self.on['istio-metadata'].relation_broken, self._on_changed
            )

        def _on_changed(self, _):
            data = self.istio_metadata.get_data()
            ...

The requirer's ``charmcraft.yaml`` should declare (with ``limit: 1``, since
``IstioMetadataRequirer`` is designed for relating to a single application)::

    requires:
      istio-metadata:
        limit: 1
        interface: istio_metadata
"""

from ._istio_metadata import (
    IstioMetadataAppData,
    IstioMetadataProvider,
    IstioMetadataRequirer,
)
from ._version import __version__ as __version__

__all__ = [
    'IstioMetadataAppData',
    'IstioMetadataProvider',
    'IstioMetadataRequirer',
]
