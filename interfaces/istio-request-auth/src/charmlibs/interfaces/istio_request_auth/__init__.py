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

"""Istio request authentication interface library.

This library provides the provider and requirer sides of the ``istio-request-auth``
relation interface for configuring Istio
`RequestAuthentication <https://istio.io/latest/docs/reference/config/security/request_authentication/>`_
resources via relation data (JWT rules, JWKS endpoints, claim-to-header mapping).

What is this library for?
=========================

The `istio-ingress-k8s <https://github.com/canonical/istio-ingress-k8s-operator/>`_ charm
wraps a `Kubernetes Gateway API <https://gateway-api.sigs.k8s.io/>`_ of class ``istio``. It
can connect to an OAuth 2.0 provider like the ``oauth2-proxy`` charm via the ``forward-auth``
relation to forward requests via an authentication stack for user authentication.

Istio also natively supports validating a pre-generated JWT against an issuer using a
``RequestAuthentication`` Kubernetes resource. This means a request containing a JWT in
the header can be natively authenticated by Istio instead of taking a detour via the
authentication stack, and the claims from the token are parsed and added as headers to
the downstream request. The `RequestAuthentication` resource is purely an Istio concept
offered by the CRDs native to Istio. Hence the interface is named with an `istio-` prefix.

For applications to take advantage of this feature, they need to tell Istio which issuers
they trust and which headers they want the claims in the token to be mapped to. To enable
this information exchange and add the appropriate ``RequestAuthentication`` resource, the
``istio-request-auth`` interface library is introduced.

Security note
=============

If a requirer is connected but has not provided valid (non-empty) ``jwt_rules``, no
``RequestAuthentication`` resource is created.  This could allow unauthenticated
traffic.  The provider exposes :meth:`~IstioRequestAuthProvider.get_connected_apps`
so the ingress charm can detect such applications and drop their ingress until valid
rules are provided.

Requirer usage::

    from charmlibs.interfaces.istio_request_auth import (
        ClaimToHeader,
        JWTRule,
        IstioRequestAuthRequirer,
    )

    class MyAppCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.request_auth = IstioRequestAuthRequirer(self)

        def _publish_rules(self):
            self.request_auth.publish_data([
                JWTRule(
                    issuer="https://accounts.example.com",
                    claim_to_headers=[
                        ClaimToHeader(header="x-user-email", claim="email"),
                    ],
                ),
            ])

Provider usage::

    from charmlibs.interfaces.istio_request_auth import IstioRequestAuthProvider

    class MyIngressCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.request_auth = IstioRequestAuthProvider(self)

        def _reconcile(self):
            valid = self.request_auth.get_data()
            connected = self.request_auth.get_connected_apps()
            invalid_apps = connected - set(valid.keys())
            # Drop ingress for invalid_apps, create RequestAuthentication for valid
"""

from ._istio_request_auth import (
    ClaimToHeader,
    FromHeader,
    IstioRequestAuthProvider,
    IstioRequestAuthRequirer,
    JWTRule,
)
from ._version import __version__ as __version__

__all__ = [
    'ClaimToHeader',
    'FromHeader',
    'IstioRequestAuthProvider',
    'IstioRequestAuthRequirer',
    'JWTRule',
]
