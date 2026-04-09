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
relation interface. Downstream applications use the requirer to publish their JWT
authentication rules, and the ingress charm uses the provider to read them.

Requirer usage::

    from charmlibs.interfaces.istio_request_auth import (
        ClaimToHeaderData,
        JWTRuleData,
        RequestAuthData,
        IstioRequestAuthRequirer,
    )

    class MyAppCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.request_auth = IstioRequestAuthRequirer(self)

        def _publish_rules(self):
            self.request_auth.publish_data(
                RequestAuthData(
                    jwt_rules=[
                        JWTRuleData(
                            issuer="https://accounts.example.com",
                            claim_to_headers=[
                                ClaimToHeaderData(header="x-user-email", claim="email"),
                            ],
                        ),
                    ]
                )
            )

Provider usage::

    from charmlibs.interfaces.istio_request_auth import IstioRequestAuthProvider

    class MyIngressCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.request_auth = IstioRequestAuthProvider(self)

        def _read_rules(self):
            if self.request_auth.is_ready:
                data = self.request_auth.get_data()
                for app_name, auth_data in data.items():
                    ...
"""

from ._istio_request_auth import (
    ClaimToHeaderData,
    FromHeaderData,
    IstioRequestAuthProvider,
    IstioRequestAuthRequirer,
    JWTRuleData,
    RequestAuthData,
)
from ._version import __version__ as __version__

__all__ = [
    'ClaimToHeaderData',
    'FromHeaderData',
    'IstioRequestAuthProvider',
    'IstioRequestAuthRequirer',
    'JWTRuleData',
    'RequestAuthData',
]
