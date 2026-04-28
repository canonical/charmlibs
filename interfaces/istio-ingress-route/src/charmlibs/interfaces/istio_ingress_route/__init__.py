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

r"""Istio ingress route interface library.

This library provides the provider and requirer sides of the ``istio-ingress-route``
relation interface for advanced ingress routing through the istio-ingress-k8s charm.

What is this library for?
=========================

The ``istio-ingress-k8s`` charm supports the standard ``ingress`` interface, but
that interface has limitations: it cannot open multiple ports, configure custom
path prefixes, apply URL rewrites or redirects, or set up gRPC routing.

The ``istio-ingress-route`` interface fills this gap. It allows requiring charms to
publish rich routing configurations — multi-port listeners, HTTP path matching,
gRPC method routing, URL rewrite filters, request redirect filters — that the
``istio-ingress-k8s`` charm translates into Kubernetes Gateway API resources
(Gateway listeners, HTTPRoutes, and GRPCRoutes).

How it works
============

1. The **requirer** charm builds an ``IstioIngressRouteConfig`` describing its
   listeners, HTTP routes, and gRPC routes, then calls ``submit_config(config)``.
2. The **provider** (istio-ingress-k8s) receives a ``ready`` event, reads the
   config via ``get_config(relation)``, and creates the corresponding Gateway API
   resources.
3. The provider publishes the external host and TLS status back to the requirer
   so it can construct its public URL.

Requirer usage::

    from charmlibs.interfaces.istio_ingress_route import (
        IstioIngressRouteRequirer,
        IstioIngressRouteConfig,
        Listener,
        HTTPRoute,
        GRPCRoute,
        BackendRef,
        ProtocolType,
        HTTPMethod,
        HTTPRouteMatch,
        HTTPPathMatch,
        HTTPPathMatchType,
        GRPCMethodMatch,
        GRPCRouteMatch,
        to_gateway_protocol,
    )

    class MyCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.ingress = IstioIngressRouteRequirer(
                self,
                relation_name="ingress",
            )
            self.framework.observe(
                self.ingress.on.ready, self._on_ingress_ready
            )

        def _configure_ingress(self):
            http_listener = Listener(port=3200, protocol=ProtocolType.HTTP)
            grpc_listener = Listener(port=9096, protocol=ProtocolType.GRPC)

            config = IstioIngressRouteConfig(
                model=self.model.name,
                listeners=[http_listener, grpc_listener],
                http_routes=[
                    HTTPRoute(
                        name="http-route",
                        listener=http_listener,
                        matches=[
                            HTTPRouteMatch(
                                path=HTTPPathMatch(
                                    type=HTTPPathMatchType.PathPrefix, value="/api"
                                ),
                                method=HTTPMethod.GET,
                            )
                        ],
                        backends=[BackendRef(service=self.app.name, port=3200)],
                    ),
                ],
                grpc_routes=[
                    GRPCRoute(
                        name="grpc-route",
                        listener=grpc_listener,
                        matches=[
                            GRPCRouteMatch(
                                method=GRPCMethodMatch(
                                    service="myapp.MyService", method="GetData"
                                )
                            )
                        ],
                        backends=[BackendRef(service=self.app.name, port=9096)],
                    ),
                ],
            )
            self.ingress.submit_config(config)

        def _on_ingress_ready(self, event):
            scheme = "https" if self.ingress.tls_enabled else "http"
            url = f"{scheme}://{self.ingress.external_host}"

Provider usage::

    from charmlibs.interfaces.istio_ingress_route import (
        IstioIngressRouteProvider,
        to_gateway_protocol,
    )

    class IstioIngressCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.istio_ingress_route = IstioIngressRouteProvider(
                self,
                external_host=self._external_host,
                tls_enabled=self._is_tls_enabled(),
            )
            self.framework.observe(
                self.istio_ingress_route.on.ready,
                self._handle_istio_ingress_route_ready,
            )

        def _handle_istio_ingress_route_ready(self, event):
            config = self.istio_ingress_route.get_config(event.relation)
            if not config:
                return
            is_tls_enabled = self._is_tls_enabled()
            for listener in config.listeners:
                gateway_protocol = to_gateway_protocol(
                    listener.protocol, is_tls_enabled
                )
"""

from ._istio_ingress_route import (
    BackendRef,
    FilterType,
    GRPCMethodMatch,
    GRPCRoute,
    GRPCRouteMatch,
    HTTPMethod,
    HTTPPathMatch,
    HTTPPathMatchType,
    HTTPRoute,
    HTTPRouteMatch,
    IstioIngressRouteConfig,
    IstioIngressRouteError,
    IstioIngressRouteProvider,
    IstioIngressRouteRequirer,
    Listener,
    PathModifier,
    PathModifierType,
    ProtocolType,
    RequestRedirectFilter,
    RequestRedirectSpec,
    UnauthorizedError,
    URLRewriteFilter,
    URLRewriteSpec,
    to_gateway_protocol,
)
from ._version import __version__ as __version__

__all__ = [
    'BackendRef',
    'FilterType',
    'GRPCMethodMatch',
    'GRPCRoute',
    'GRPCRouteMatch',
    'HTTPMethod',
    'HTTPPathMatch',
    'HTTPPathMatchType',
    'HTTPRoute',
    'HTTPRouteMatch',
    'IstioIngressRouteConfig',
    'IstioIngressRouteError',
    'IstioIngressRouteProvider',
    'IstioIngressRouteRequirer',
    'Listener',
    'PathModifier',
    'PathModifierType',
    'ProtocolType',
    'RequestRedirectFilter',
    'RequestRedirectSpec',
    'URLRewriteFilter',
    'URLRewriteSpec',
    'UnauthorizedError',
    'to_gateway_protocol',
]
