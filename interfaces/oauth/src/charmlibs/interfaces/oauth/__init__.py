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


"""Oauth Library.

This library is designed to enable applications to register OAuth2/OIDC
clients with an OIDC Provider through the ``oauth`` interface.

Getting started
---------------

To get started using this library you just need to fetch the library using ``charmcraft``.

.. note::
   You also need to add ``jsonschema`` to your charm's ``requirements.txt``.

.. code-block:: shell

    cd some-charm
    charmcraft fetch-lib charms.hydra.v0.oauth

Then, to initialize the library:

.. code-block:: python

    # ...
    from charms.hydra.v0.oauth import ClientConfig, OAuthRequirer

    OAUTH = "oauth"
    OAUTH_SCOPES = "openid email"
    OAUTH_GRANT_TYPES = ["authorization_code"]

    class SomeCharm(CharmBase):
        def __init__(self, *args):
            # ...
            self.oauth = OAuthRequirer(self, client_config, relation_name=OAUTH)

            self.framework.observe(self.oauth.on.oauth_info_changed, self._configure_application)
            # ...

        def _on_ingress_ready(self, event):
            self.external_url = "https://example.com"
            self._set_client_config()

        def _set_client_config(self):
            client_config = ClientConfig(
                urljoin(self.external_url, "/oauth/callback"),
                OAUTH_SCOPES,
                OAUTH_GRANT_TYPES,
            )
            self.oauth.update_client_config(client_config)
"""

from ._oauth import (
    ClientChangedEvent,
    ClientConfig,
    ClientConfigError,
    ClientCreatedEvent,
    ClientDeletedEvent,
    DataValidationError,
    InvalidClientConfigEvent,
    OAuthInfoChangedEvent,
    OAuthInfoRemovedEvent,
    OAuthProvider,
    OauthProviderConfig,
    OAuthProviderEvents,
    OAuthRequirer,
    OAuthRequirerEvents,
)
from ._version import __version__ as __version__

__all__ = [
    'ClientChangedEvent',
    'ClientConfig',
    'ClientConfigError',
    'ClientCreatedEvent',
    'ClientDeletedEvent',
    'DataValidationError',
    'InvalidClientConfigEvent',
    'OAuthInfoChangedEvent',
    'OAuthInfoRemovedEvent',
    'OAuthProvider',
    'OAuthProviderEvents',
    'OAuthRequirer',
    'OAuthRequirerEvents',
    'OauthProviderConfig',
]
