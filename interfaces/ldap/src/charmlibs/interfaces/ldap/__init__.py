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

"""The charmlibs.interfaces.ldap package.

Juju Charm Library for the `ldap` Juju Interface
================================================

This Juju charm library contains the Provider and Requirer classes for handling
the ``ldap`` interface.

Requirer Charm
--------------

The requirer charm is expected to:

- Provide information for the provider charm to deliver LDAP related
  information in the juju integration, in order to communicate with the LDAP
  server and authenticate LDAP operations
- Listen to the custom juju event ``LdapReadyEvent`` to obtain the LDAP
  related information from the integration
- Listen to the custom juju event ``LdapUnavailableEvent`` to handle the
  situation when the LDAP integration is broken

.. code-block:: python

    from charmlibs.interfaces.ldap import (
        LdapRequirer,
        LdapReadyEvent,
        LdapUnavailableEvent,
    )

    class RequirerCharm(CharmBase):
        # LDAP requirer charm that integrates with an LDAP provider charm.

        def __init__(self, *args):
            super().__init__(*args)

            self.ldap_requirer = LdapRequirer(self)
            self.framework.observe(
                self.ldap_requirer.on.ldap_ready,
                self._on_ldap_ready,
            )
            self.framework.observe(
                self.ldap_requirer.on.ldap_unavailable,
                self._on_ldap_unavailable,
            )

        def _on_ldap_ready(self, event: LdapReadyEvent) -> None:
            # Consume the LDAP related information
            ldap_data = self.ldap_requirer.consume_ldap_relation_data(
                relation=event.relation,
            )

            # Configure the LDAP requirer charm
            ...

        def _on_ldap_unavailable(self, event: LdapUnavailableEvent) -> None:
            # Handle the situation where the LDAP integration is broken
            ...

As shown above, the library offers custom juju events to handle specific
situations, which are listed below:

- ``ldap_ready``: event emitted when the LDAP related information is ready for
  requirer charm to use.
- ``ldap_unavailable``: event emitted when the LDAP integration is broken.

Additionally, the requirer charmed operator needs to declare the ``ldap``
interface in the ``metadata.yaml``:

.. code-block:: yaml

    requires:
      ldap:
        interface: ldap

Provider Charm
--------------

The provider charm is expected to:

- Use the information provided by the requirer charm to provide LDAP related
  information for the requirer charm to connect and authenticate to the LDAP
  server
- Listen to the custom juju event ``LdapRequestedEvent`` to offer LDAP related
  information in the integration

.. code-block:: python

    from charmlibs.interfaces.ldap import (
        LdapProvider,
        LdapRequestedEvent,
    )

    class ProviderCharm(CharmBase):
        # LDAP provider charm.

        def __init__(self, *args):
            super().__init__(*args)

            self.ldap_provider = LdapProvider(self)
            self.framework.observe(
                self.ldap_provider.on.ldap_requested,
                self._on_ldap_requested,
            )

        def _on_ldap_requested(self, event: LdapRequestedEvent) -> None:
            # Consume the information provided by the requirer charm
            requirer_data = event.data

            # Prepare the LDAP related information using the requirer's data
            ldap_data = ...

            # Update the integration data
            self.ldap_provider.update_relations_app_data(
                relation.id,
                ldap_data,
            )

As shown above, the library offers custom juju events to handle specific
situations, which are listed below:

- ``ldap_requested``: event emitted when the requirer charm is requesting the
  LDAP related information in order to connect and authenticate to the LDAP server.
"""

from ._ldap import (
    DEFAULT_RELATION_NAME,
    LdapProvider,
    LdapProviderBaseData,
    LdapProviderData,
    LdapReadyEvent,
    LdapRequestedEvent,
    LdapRequirer,
    LdapRequirerData,
    LdapUnavailableEvent,
)
from ._version import __version__ as __version__

__all__ = [
    'DEFAULT_RELATION_NAME',
    'LdapProvider',
    'LdapProviderBaseData',
    'LdapProviderData',
    'LdapReadyEvent',
    'LdapRequestedEvent',
    'LdapRequirer',
    'LdapRequirerData',
    'LdapUnavailableEvent',
]
