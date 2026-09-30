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

"""Interface library for providing OAuth2 Proxy with downstream charms' auth-proxy information.

It is required to integrate a charm into an Identity and Access Proxy (IAP).

Getting Started
---------------

To install, add `charmlibs-interfaces-auth-proxy` to your Python dependencies.
Then in your Python code, import as:

.. code-block:: python

    from charmlibs.interfaces import auth_proxy

**Note that you also need to add ``jsonschema`` to your charm's ``requirements.txt``.**

To use the library from the requirer side, add the following to the ``metadata.yaml`` of the charm:

.. code-block:: yaml

    requires:
      auth-proxy:
        interface: auth_proxy
        limit: 1

Then, to initialise the library:

.. code-block:: python

    from charmlibs.interfaces.auth_proxy import AuthProxyConfig, AuthProxyRequirer

    AUTH_PROXY_ALLOWED_ENDPOINTS = ["welcome", "about/app"]
    AUTH_PROXY_HEADERS = ["X-Auth-Request-User", "X-Auth-Request-Email"]
    AUTH_PROXY_AUTHENTICATED_EMAILS = ["test@example.com", "test@canonical.com"]
    AUTH_PROXY_AUTHENTICATED_EMAIL_DOMAINS = ["canonical.com"]

    class SomeCharm(CharmBase):
        def __init__(self, *args):
            # ...
            self.auth_proxy = AuthProxyRequirer(self, self._auth_proxy_config)

        @property
        def external_urls(self) -> list:
            # Get ingress-per-unit or externally-configured web urls
            # ...
            return ["https://example.com/unit-0", "https://example.com/unit-1"]

        @property
        def _auth_proxy_config(self) -> AuthProxyConfig:
            return AuthProxyConfig(
                protected_urls=self.external_urls,
                allowed_endpoints=AUTH_PROXY_ALLOWED_ENDPOINTS,
                headers=AUTH_PROXY_HEADERS,
                authenticated_emails=AUTH_PROXY_AUTHENTICATED_EMAILS,
                authenticated_email_domains=AUTH_PROXY_AUTHENTICATED_EMAIL_DOMAINS
            )

        def _on_ingress_ready(self, event):
            self._configure_auth_proxy()

        def _configure_auth_proxy(self):
            self.auth_proxy.update_auth_proxy_config(auth_proxy_config=self._auth_proxy_config)
"""

from ._auth_proxy import (
    AuthProxyConfig,
    AuthProxyConfigChangedEvent,
    AuthProxyConfigError,
    AuthProxyConfigRemovedEvent,
    AuthProxyProvider,
    AuthProxyRelationRemovedEvent,
    AuthProxyRequirer,
    InvalidAuthProxyConfigEvent,
)
from ._version import __version__ as __version__

__all__ = [
    'AuthProxyConfig',
    'AuthProxyConfigChangedEvent',
    'AuthProxyConfigError',
    'AuthProxyConfigRemovedEvent',
    'AuthProxyProvider',
    'AuthProxyRelationRemovedEvent',
    'AuthProxyRequirer',
    'InvalidAuthProxyConfigEvent',
]
