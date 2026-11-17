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

"""Interface Library for OpenFGA.

This library wraps relation endpoints using the ``openfga`` interface
and provides a Python API for requesting OpenFGA authorization model
stores to be created.

Getting Started
---------------

To get started using the library, you just need to fetch the library using ``charmcraft``:

.. code-block:: shell

    cd some-charm
    charmcraft fetch-lib charms.openfga_k8s.v1.openfga

In the ``metadata.yaml`` of the charm, add the following:

.. code-block:: yaml

    requires:
      openfga:
        interface: openfga

Then, to initialise the library:

.. code-block:: python

    from charms.openfga_k8s.v1.openfga import (
        OpenFGARequires,
        OpenFGAStoreCreateEvent,
    )

    class SomeCharm(CharmBase):
        def __init__(self, *args):
            # ...
            self.openfga = OpenFGARequires(self, "test-openfga-store")
            self.framework.observe(
                self.openfga.on.openfga_store_created,
                self._on_openfga_store_created,
            )

        def _on_openfga_store_created(self, event: OpenFGAStoreCreateEvent):
            if not event.store_id:
                return

            info = self.openfga.get_store_info()
            if not info:
                return

            logger.info("store id {}".format(info.store_id))
            logger.info("token {}".format(info.token))
            logger.info("grpc_api_url {}".format(info.grpc_api_url))
            logger.info("http_api_url {}".format(info.http_api_url))
"""

from ._openfga import (
    DEFAULT_INTEGRATION_NAME,
    OpenFGAProvider,
    OpenfgaProviderAppData,
    OpenfgaProviderBaseData,
    OpenfgaRequirerAppData,
    OpenFGARequires,
    OpenFGAStoreCreateEvent,
    OpenFGAStoreRemovedEvent,
    OpenFGAStoreRequestEvent,
)
from ._version import __version__ as __version__

__all__ = [
    'DEFAULT_INTEGRATION_NAME',
    'OpenFGAProvider',
    'OpenFGARequires',
    'OpenFGAStoreCreateEvent',
    'OpenFGAStoreRemovedEvent',
    'OpenFGAStoreRequestEvent',
    'OpenfgaProviderAppData',
    'OpenfgaProviderBaseData',
    'OpenfgaRequirerAppData',
]
