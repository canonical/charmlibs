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

"""Interface library for providing API Gateways with Identity and Access Proxy information.

It is required to integrate with OAuth2 Proxy - a reverse proxy and static file server that provides authentication
using Identity Platform's built-in identity management system and integrated identity providers (Google, GitHub, and others).

Getting Started
===============

To use the library from the requirer side, add the following to the ``metadata.yaml`` of the charm:

.. code-block:: yaml

    requires:
      forward-auth:
        interface: forward_auth
        limit: 1

Then, to initialise the library:

.. code-block:: python

    from charmlibs.interfaces.forward_auth import AuthConfigChangedEvent, ForwardAuthRequirer

    class ApiGatewayCharm(CharmBase):
        def __init__(self, *args):
            # ...
            self.forward_auth = ForwardAuthRequirer(self)
            self.framework.observe(
                self.forward_auth.on.auth_config_changed,
                self.some_event_function
                )

        def some_event_function(self, event: AuthConfigChangedEvent):
            if self.forward_auth.is_ready():
                # Fetch the relation info
                forward_auth_data = self.forward_auth.get_provider_info()
                # update ingress configuration
                # ...
"""

from ._forward_auth import (
    INTERFACE_NAME,
    RELATION_NAME,
    AuthConfigChangedEvent,
    AuthConfigRemovedEvent,
    ForwardAuthConfig,
    ForwardAuthConfigError,
    ForwardAuthProvider,
    ForwardAuthProxySet,
    ForwardAuthRelationRemovedEvent,
    ForwardAuthRequirer,
    ForwardAuthRequirerConfig,
    InvalidForwardAuthConfigEvent,
)
from ._version import __version__ as __version__

__all__ = [
    'INTERFACE_NAME',
    'RELATION_NAME',
    'AuthConfigChangedEvent',
    'AuthConfigRemovedEvent',
    'ForwardAuthConfig',
    'ForwardAuthConfigError',
    'ForwardAuthProvider',
    'ForwardAuthProxySet',
    'ForwardAuthRelationRemovedEvent',
    'ForwardAuthRequirer',
    'ForwardAuthRequirerConfig',
    'InvalidForwardAuthConfigEvent',
]
