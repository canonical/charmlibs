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

"""Istio ingress config interface library.

This library provides the provider and requirer sides of the ``istio-ingress-config``
relation interface for exchanging external authorizer configuration between an Istio
ingress charm and the Istio control plane charm.

What is this library for?
=========================

The `istio-ingress-k8s <https://github.com/canonical/istio-ingress-k8s-operator/>`_ charm
needs to pass information about the external authentication provider to the
`istio-k8s <https://github.com/canonical/istio-k8s-operator/>`_ core charm so the Istio
control plane can be configured with an external authorizer.

The ``istio-ingress-config`` interface connects the ``istio-ingress-k8s`` charm to the
``istio-k8s`` charm, allowing the ingress to inform the control plane about the external
auth decision provider with information including the decision service address, port,
and header forwarding rules (which headers to include in auth checks, which headers to
forward upstream/downstream on allow/deny decisions).

Provider usage (ingress charm)::

    from charmlibs.interfaces.istio_ingress_config import IngressConfigProvider

    class MyIngressCharm(CharmBase):
        def __init__(self, framework):
            super().__init__(framework)
            self.ingress_config = IngressConfigProvider(
                self.model.relations, self.app, "istio-ingress-config"
            )

        def _publish(self):
            self.ingress_config.publish(
                ext_authz_service_name="my-ext-authz-service",
                ext_authz_port="8080",
            )

Requirer usage (control plane charm)::

    from charmlibs.interfaces.istio_ingress_config import IngressConfigRequirer

    class MyControlPlaneCharm(CharmBase):
        def __init__(self, framework):
            super().__init__(framework)
            self.ingress_config = IngressConfigRequirer(
                self.model.relations, self.app, "istio-ingress-config"
            )

        def _on_relation_changed(self, event):
            for relation in self.ingress_config.relations:
                if self.ingress_config.is_ready(relation):
                    ext_authz_info = self.ingress_config.get_provider_ext_authz_info(relation)
                    ...
"""

from ._istio_ingress_config import (
    DEFAULT_HEADERS_TO_DOWNSTREAM_ON_ALLOW,
    DEFAULT_HEADERS_TO_DOWNSTREAM_ON_DENY,
    DEFAULT_HEADERS_TO_UPSTREAM_ON_ALLOW,
    DEFAULT_INCLUDE_HEADERS_IN_CHECK,
    IngressConfigProvider,
    IngressConfigRequirer,
    ProviderIngressConfigData,
)
from ._version import __version__ as __version__

__all__ = [
    'DEFAULT_HEADERS_TO_DOWNSTREAM_ON_ALLOW',
    'DEFAULT_HEADERS_TO_DOWNSTREAM_ON_DENY',
    'DEFAULT_HEADERS_TO_UPSTREAM_ON_ALLOW',
    'DEFAULT_INCLUDE_HEADERS_IN_CHECK',
    'IngressConfigProvider',
    'IngressConfigRequirer',
    'ProviderIngressConfigData',
]
