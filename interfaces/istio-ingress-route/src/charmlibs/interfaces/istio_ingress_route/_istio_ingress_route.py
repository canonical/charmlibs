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

"""Istio ingress route interface implementation.

Migrated from charms.istio_ingress_k8s.v0.istio_ingress_route.
"""

import logging
from abc import ABC
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from ops.charm import CharmBase, CharmEvents, RelationEvent
from ops.framework import EventSource, Object, StoredState
from pydantic import BaseModel, Field, computed_field, model_serializer, model_validator

if TYPE_CHECKING:
    from ops.model import Relation

log = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Exceptions
# -------------------------------------------------------------------
class IstioIngressRouteError(RuntimeError):
    """Base class for exceptions raised by IstioIngressRoute."""


class UnauthorizedError(IstioIngressRouteError):
    """Raised when the unit needs the leader to perform some action."""


# -------------------------------------------------------------------
# Enums and Helper Functions
# -------------------------------------------------------------------
class ProtocolType(str, Enum):
    """Application-level protocol types.

    Consumers specify the application protocol (HTTP or GRPC).
    The istio-ingress charm automatically applies TLS encryption based on
    certificate availability, upgrading HTTP to HTTPS and GRPC to GRPCS
    transparently.

    The Gateway API doesn't have GRPC as a distinct protocol type.
    GRPC uses HTTP/2, so it maps to "HTTP" or "HTTPS" in Gateway listeners.
    The difference between HTTP and gRPC traffic is expressed through the
    route type (HTTPRoute vs GRPCRoute).
    """

    HTTP = 'HTTP'
    GRPC = 'GRPC'


def to_gateway_protocol(protocol: ProtocolType, tls_enabled: bool = False) -> str:
    """Map application protocol to Gateway API protocol.

    The Gateway API doesn't have separate HTTP/gRPC protocol types.
    Both use HTTP, with the difference being in the route type (HTTPRoute vs GRPCRoute).

    Args:
        protocol: Application-level protocol (HTTP or GRPC)
        tls_enabled: Whether TLS termination should be applied

    Returns:
        Gateway API protocol string ("HTTP" or "HTTPS")

    Examples:
        >>> to_gateway_protocol(ProtocolType.HTTP, tls_enabled=False)
        'HTTP'
        >>> to_gateway_protocol(ProtocolType.HTTP, tls_enabled=True)
        'HTTPS'
        >>> to_gateway_protocol(ProtocolType.GRPC, tls_enabled=False)
        'HTTP'
        >>> to_gateway_protocol(ProtocolType.GRPC, tls_enabled=True)
        'HTTPS'
    """
    if tls_enabled:
        return 'HTTPS'
    else:
        return 'HTTP'


# -------------------------------------------------------------------
# Base Models
# -------------------------------------------------------------------
class Listener(BaseModel):
    """Gateway listener configuration.

    Specify the application-level protocol (HTTP or GRPC).
    The istio-ingress charm will automatically upgrade to TLS (HTTPS/GRPCS)
    when certificates are available.

    The listener name is automatically derived from port and protocol by the charm.
    """

    port: int = Field(ge=1, le=65535, description='Port number')
    protocol: ProtocolType = Field(description='Protocol type')

    @property
    def name(self) -> str:
        """Get the listener name derived from protocol and port.

        Returns:
            Listener name in format: {protocol}-{port} (e.g., "http-8080", "grpc-9090")
        """
        return f'{self.protocol.value.lower()}-{self.port}'

    @property
    def gateway_protocol(self) -> str:
        """Get the Gateway API protocol (cleartext).

        This maps GRPC -> HTTP, since Gateway API doesn't have a GRPC protocol type.
        Both HTTP and gRPC use HTTP/2; the difference is in the route type.

        Returns:
            Gateway API protocol string without TLS ("HTTP")
        """
        return to_gateway_protocol(self.protocol, tls_enabled=False)


class BackendRef(BaseModel):
    """Reference to a backend service."""

    service: str = Field(description='Service name (in same namespace)')
    port: int = Field(ge=1, le=65535, description='Service port')
    weight: int | None = Field(default=None, ge=1, le=100, description='Traffic weight')


# -------------------------------------------------------------------
# Route Rule Base Classes
# -------------------------------------------------------------------
# Match helpers
class HTTPMethod(str, Enum):
    """HTTP methods for route matching."""

    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'
    PATCH = 'PATCH'
    HEAD = 'HEAD'
    OPTIONS = 'OPTIONS'
    CONNECT = 'CONNECT'
    TRACE = 'TRACE'


class HTTPPathMatchType(str, Enum):
    """Path match types for HTTP routes."""

    Exact = 'Exact'
    PathPrefix = 'PathPrefix'
    RegularExpression = 'RegularExpression'


class HTTPPathMatch(BaseModel):
    """Path matching configuration for HTTP routes."""

    type: HTTPPathMatchType = Field(
        default=HTTPPathMatchType.PathPrefix,
        description='Type of path match (Exact, PathPrefix, or RegularExpression)',
    )
    value: str = Field(description='Path value to match')


class GRPCMethodMatch(BaseModel):
    """gRPC method matching configuration.

    Matches gRPC methods in the format /service/method where:
    - service can be a simple name (e.g., "MyService") or package-qualified
      (e.g., "package.MyService")
    - method is the RPC method name (optional - if omitted, matches all methods
      on the service)

    Examples:
        >>> GRPCMethodMatch(service="com.example.UserService")
        # Matches all methods on /com.example.UserService

        >>> GRPCMethodMatch(service="com.example.UserService", method="GetUser")
        # Matches only /com.example.UserService/GetUser

        >>> GRPCMethodMatch(service="UserService", method="CreateUser")
        # Matches /UserService/CreateUser
    """

    service: str = Field(description="gRPC service name (e.g., 'package.Service')")
    method: str | None = Field(
        default=None,
        description=(
            "gRPC method name (e.g., 'GetUser'). If omitted, matches all methods on the service"
        ),
    )


class _RouteMatch(BaseModel, ABC):
    """Base class for route match conditions."""

    headers: dict[str, str] | None = Field(default=None, description='Header matches')


class HTTPRouteMatch(_RouteMatch):
    """Match conditions for HTTP routes."""

    path: HTTPPathMatch | None = Field(default=None, description='Path match configuration')
    method: HTTPMethod | None = Field(default=None, description='HTTP method')


class GRPCRouteMatch(_RouteMatch):
    """Match conditions for gRPC routes."""

    method: GRPCMethodMatch | None = Field(
        default=None, description='gRPC method match configuration'
    )


# Filter helpers
class PathModifierType(str, Enum):
    """Path modifier types."""

    ReplaceFullPath = 'ReplaceFullPath'
    ReplacePrefixMatch = 'ReplacePrefixMatch'


class PathModifier(BaseModel):
    """Path modification configuration."""

    type: PathModifierType = Field(description='Type of path modification')
    value: str = Field(description='Replacement value for the path')

    @model_validator(mode='before')
    @classmethod
    def validate_path_modifier(cls, data: Any) -> Any:
        """Handle deserialization from K8s Gateway API format."""
        if not isinstance(data, dict):
            return data
        d = cast('dict[str, Any]', data)
        if 'replacePrefixMatch' in d:
            return {
                'type': d.get('type', PathModifierType.ReplacePrefixMatch),
                'value': d['replacePrefixMatch'],
            }
        if 'replaceFullPath' in d:
            return {
                'type': d.get('type', PathModifierType.ReplaceFullPath),
                'value': d['replaceFullPath'],
            }
        return d

    @model_serializer
    def serialize_model(self) -> dict[str, str]:
        """Serialize with correct field name for K8s Gateway API."""
        if self.type == PathModifierType.ReplaceFullPath:
            return {
                'type': self.type.value,
                'replaceFullPath': self.value,
            }
        return {
            'type': self.type.value,
            'replacePrefixMatch': self.value,
        }


class FilterType(str, Enum):
    """Filter type values."""

    URLRewrite = 'URLRewrite'
    RequestRedirect = 'RequestRedirect'


class URLRewriteSpec(BaseModel):
    """Specification for URL rewrite configuration.

    At least one of hostname or path must be specified.
    """

    hostname: str | None = Field(default=None, description='Hostname to rewrite the request to')
    path: PathModifier | None = Field(default=None, description='Path modification configuration')


class URLRewriteFilter(BaseModel):
    """URLRewrite filter for modifying request URL before proxying upstream."""

    urlRewrite: URLRewriteSpec = Field(description='URL rewrite specification')  # noqa: N815

    @computed_field
    @property
    def type(self) -> FilterType:
        """Filter type."""
        return FilterType.URLRewrite


class RequestRedirectSpec(BaseModel):
    """Specification for request redirect configuration."""

    scheme: str | None = Field(default=None, description='Scheme to redirect to (http or https)')
    hostname: str | None = Field(default=None, description='Hostname to redirect to')
    path: PathModifier | None = Field(default=None, description='Path modification for redirect')
    port: int | None = Field(default=None, ge=1, le=65535, description='Port to redirect to')
    statusCode: int = Field(  # noqa: N815
        default=301, description='HTTP status code for redirect (default 301)'
    )


class RequestRedirectFilter(BaseModel):
    """Request redirect filter for HTTP/gRPC redirects."""

    requestRedirect: RequestRedirectSpec = Field(  # noqa: N815
        description='Request redirect specification'
    )

    @computed_field
    @property
    def type(self) -> FilterType:
        """Filter type."""
        return FilterType.RequestRedirect


HTTPRouteFilter = URLRewriteFilter | RequestRedirectFilter
GRPCRouteFilter = RequestRedirectFilter


# -------------------------------------------------------------------
# Route Base Classes
# -------------------------------------------------------------------
class _Route(BaseModel, ABC):
    """Base class for all routes."""

    name: str = Field(description='Route name')
    listener: Listener = Field(description='Listener this route binds to')
    backends: list[BackendRef] = Field(description='Backend services')

    @property
    def protocol(self) -> ProtocolType:
        """Protocol type - overridden in subclasses."""
        raise NotImplementedError


class _L7Route(_Route, ABC):
    """Base class for Layer 7 routes."""

    hostnames: list[str] | None = Field(default=None, description='Hostnames to match')


# -------------------------------------------------------------------
# Concrete Route Classes
# -------------------------------------------------------------------
class HTTPRoute(_L7Route):
    """HTTP route configuration."""

    matches: list[HTTPRouteMatch] | None = Field(default=None, description='HTTP match rules')
    filters: list[HTTPRouteFilter] | None = Field(
        default=None, description='Filters to apply to requests matching this route'
    )

    @property
    def protocol(self) -> ProtocolType:
        """Protocol type for HTTP routes."""
        return ProtocolType.HTTP


class GRPCRoute(_L7Route):
    """gRPC route configuration."""

    matches: list[GRPCRouteMatch] | None = Field(default=None, description='gRPC match rules')
    filters: list[GRPCRouteFilter] | None = Field(
        default=None, description='Filters to apply to requests matching this route'
    )

    @property
    def protocol(self) -> ProtocolType:
        """Protocol type for gRPC routes."""
        return ProtocolType.GRPC


# -------------------------------------------------------------------
# Main Config
# -------------------------------------------------------------------
class IstioIngressRouteConfig(BaseModel):
    """Complete configuration for istio-ingress-route."""

    model: str = Field(description='The model (namespace) where backend services live')
    listeners: list[Listener] = Field(default_factory=lambda: list[Listener]())
    http_routes: list[HTTPRoute] = Field(default_factory=lambda: list[HTTPRoute]())
    grpc_routes: list[GRPCRoute] = Field(default_factory=lambda: list[GRPCRoute]())


# -------------------------------------------------------------------
# Events
# -------------------------------------------------------------------
class _IstioIngressRouteProviderReadyEvent(RelationEvent):
    """Event emitted when istio-ingress is ready to provide ingress for a routed unit."""


class _IstioIngressRouteProviderDataRemovedEvent(RelationEvent):
    """Event emitted when a routed ingress relation is removed."""


class _IstioIngressRouteRequirerReadyEvent(RelationEvent):
    """Event emitted when a unit requesting ingress has provided all data."""


class _IstioIngressRouteRequirerEvents(CharmEvents):
    """Container for IstioIngressRouteRequirer events."""

    ready = EventSource(_IstioIngressRouteRequirerReadyEvent)


class _IstioIngressRouteProviderEvents(CharmEvents):
    """Container for IstioIngressRouteProvider events."""

    ready = EventSource(_IstioIngressRouteProviderReadyEvent)
    data_removed = EventSource(_IstioIngressRouteProviderDataRemovedEvent)


# -------------------------------------------------------------------
# Provider
# -------------------------------------------------------------------
class IstioIngressRouteProvider(Object):
    """Implementation of the provider of istio_ingress_route.

    This will be owned by the istio-ingress charm.
    The main idea is that istio-ingress will observe the `ready` event and, upon
    receiving it, will fetch the config from the requirer's application databag,
    apply it (create Gateway listeners and Routes), and update its own app databag
    to let the requirer know that the ingress is ready.
    """

    on = _IstioIngressRouteProviderEvents()  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
    _stored = StoredState()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = 'istio-ingress-route',
        external_host: str = '',
        *,
        tls_enabled: bool = False,
    ):
        """Constructor for IstioIngressRouteProvider.

        Args:
            charm: The charm that is instantiating the instance.
            relation_name: The name of the relation to bind to
                (defaults to "istio-ingress-route").
            external_host: The external host.
            tls_enabled: Whether TLS is enabled on the gateway.
        """
        super().__init__(charm, relation_name)
        self._stored.set_default(external_host=None, tls_enabled=None)

        self._charm = charm
        self._relation_name = relation_name

        if self._stored.external_host != external_host or self._stored.tls_enabled != tls_enabled:
            # If istio-ingress endpoint details changed, update
            self.update_ingress_address(external_host=external_host, tls_enabled=tls_enabled)

        self.framework.observe(
            self._charm.on[relation_name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            self._charm.on[relation_name].relation_broken, self._on_relation_broken
        )

    @property
    def external_host(self) -> str:
        """Return the external host set by istio-ingress, if any."""
        self._update_stored()
        return self._stored.external_host or ''

    @property
    def tls_enabled(self) -> bool:
        """Return whether TLS is enabled on the gateway."""
        self._update_stored()
        return self._stored.tls_enabled or False

    @property
    def relations(self):
        """The list of Relation instances associated with this endpoint."""
        return list(self._charm.model.relations[self._relation_name])

    def _update_stored(self) -> None:
        """Ensure that the stored data is up-to-date."""
        if not self._charm.unit.is_leader():
            return

        for relation in self._charm.model.relations[self._relation_name]:
            if not relation.app:
                self._stored.external_host = ''
                self._stored.tls_enabled = False
                return
            external_host = relation.data[relation.app].get('external_host', '')
            self._stored.external_host = external_host or self._stored.external_host
            tls_enabled_str = relation.data[relation.app].get('tls_enabled', 'False')
            self._stored.tls_enabled = tls_enabled_str == 'True'

    def _on_relation_changed(self, event: RelationEvent):
        if self.is_ready(event.relation):
            self.update_ingress_address()
            self.on.ready.emit(relation=event.relation, app=event.relation.app)

    def _on_relation_broken(self, event: RelationEvent):
        self.on.data_removed.emit(relation=event.relation, app=event.relation.app)

    def update_ingress_address(
        self, *, external_host: str | None = None, tls_enabled: bool | None = None
    ):
        """Ensure that requirers know the external host for istio-ingress."""
        if not self._charm.unit.is_leader():
            return

        for relation in self._charm.model.relations[self._relation_name]:
            relation.data[self._charm.app]['external_host'] = external_host or self.external_host
            tls_value = tls_enabled if tls_enabled is not None else self.tls_enabled
            relation.data[self._charm.app]['tls_enabled'] = str(tls_value)

        # We first attempt to write relation data (which may raise) and only then update stored
        # state.
        self._stored.external_host = external_host
        self._stored.tls_enabled = tls_enabled

    def wipe_ingress_data(self, relation: 'Relation'):
        """Clear ingress data from relation.

        This removes the external_host and tls_enabled fields from the provider's
        application databag for the given relation. This is typically used when
        route conflicts are detected or when the ingress should no longer be available.

        Args:
            relation: The relation to clear data from
        """
        if not self._charm.unit.is_leader():
            log.debug('wipe_ingress_data: not leader, skipping')
            return

        try:
            relation.data[self._charm.app].pop('external_host', None)
            relation.data[self._charm.app].pop('tls_enabled', None)
        except Exception as e:
            log.warning(
                'Error %s clearing ingress data for relation %s. '
                'This may be a ghost of a dead relation.',
                e,
                relation.name,
            )

    def is_ready(self, relation: 'Relation') -> bool:
        """Whether IstioIngressRoute is ready on this relation.

        Returns True when the remote app shared the config; False otherwise.
        """
        if not relation.app or not relation.data[relation.app]:
            return False
        return 'config' in relation.data[relation.app]

    def get_config(self, relation: 'Relation') -> IstioIngressRouteConfig | None:
        """Retrieve the config published by the remote application."""
        if not self.is_ready(relation):
            return None

        config_json = relation.data[relation.app].get('config')
        if not config_json:
            return None

        try:
            return IstioIngressRouteConfig.model_validate_json(config_json)
        except Exception as e:
            log.error('Failed to parse config from %s: %s', relation, e)
            return None


# -------------------------------------------------------------------
# Requirer
# -------------------------------------------------------------------
class IstioIngressRouteRequirer(Object):
    """Handles the requirer side of the istio-ingress-route interface.

    This class provides an API for publishing routing configurations
    to the istio-ingress charm through the `istio-ingress-route` relation.
    """

    on = _IstioIngressRouteRequirerEvents()  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
    _stored = StoredState()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = 'ingress',
    ):
        """Constructor for IstioIngressRouteRequirer.

        Args:
            charm: The charm that is instantiating the instance.
            relation_name: The name of the relation to bind to (defaults to "ingress").
        """
        super().__init__(charm, relation_name)
        self._stored.set_default(external_host=None, tls_enabled=None)

        self._charm = charm
        self._relation_name = relation_name

        self.framework.observe(
            self._charm.on[relation_name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            self._charm.on[relation_name].relation_broken, self._on_relation_broken
        )

    @property
    def external_host(self) -> str:
        """Return the external host set by istio-ingress, if any."""
        self._update_stored()
        return self._stored.external_host or ''

    @property
    def tls_enabled(self) -> bool:
        """Return whether TLS is enabled on the gateway."""
        self._update_stored()
        return self._stored.tls_enabled or False

    def _update_stored(self) -> None:
        """Ensure that the stored host is up-to-date."""
        if not self._charm.unit.is_leader():
            return

        for relation in self._charm.model.relations[self._relation_name]:
            if not relation.app:
                self._stored.external_host = ''
                self._stored.tls_enabled = False
                return
            external_host = relation.data[relation.app].get('external_host', '')
            self._stored.external_host = external_host or self._stored.external_host
            tls_enabled_str = relation.data[relation.app].get('tls_enabled', 'False')
            self._stored.tls_enabled = tls_enabled_str == 'True'

    def _on_relation_changed(self, event: RelationEvent) -> None:
        """Update StoredState with external_host and other information from istio-ingress."""
        self._update_stored()
        if self._charm.unit.is_leader():
            self.on.ready.emit(relation=event.relation, app=event.relation.app)

    def _on_relation_broken(self, event: RelationEvent) -> None:
        """On RelationBroken, clear the stored data if set and emit an event."""
        self._stored.external_host = ''
        self._stored.tls_enabled = False
        if self._charm.unit.is_leader():
            self.on.ready.emit(relation=event.relation, app=event.relation.app)

    def is_ready(self) -> bool:
        """Is the IstioIngressRouteRequirer ready to submit data?"""
        return len(self._charm.model.relations[self._relation_name]) > 0

    def submit_config(self, config: IstioIngressRouteConfig):
        """Submit an ingress configuration to istio-ingress.

        This method publishes routing configuration data to the
        `istio-ingress-route` relation.

        Args:
            config: The IstioIngressRouteConfig to submit.

        Raises:
            UnauthorizedError: If the unit is not the leader.
        """
        if not self._charm.unit.is_leader():
            raise UnauthorizedError()

        relations = self._charm.model.relations[self._relation_name]
        if not relations:
            log.warning('No relations found for %s', self._relation_name)
            return

        for relation in relations:
            app_databag = relation.data[self._charm.app]
            # Serialize to JSON using Pydantic v2
            app_databag['config'] = config.model_dump_json()
