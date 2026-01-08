# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Source code of `charmlibs.interfaces.http_endpoint` v1.0.0."""

import logging

from ops import CharmBase, CharmEvents, EventBase, EventSource, Object
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class InvalidHttpEndpointDataError(Exception):
    """Exception raised for invalid http_endpoint data."""


class HttpEndpointDataModel(BaseModel):
    """Data model for http_endpoint interface."""

    port: str
    scheme: str
    hostname: str

    @field_validator('port')
    @classmethod
    def validate_port(cls, value: str) -> str:
        """Validate that port is in the valid range [1, 65535]."""
        if not (1 <= int(value) <= 65535):
            raise InvalidHttpEndpointDataError(f'Invalid port: {value}')
        return value

    @field_validator('scheme')
    @classmethod
    def validate_scheme(cls, value: str) -> str:
        """Validate that scheme is either 'http' or 'https'."""
        valid_schemes = {'http', 'https'}
        if value not in valid_schemes:
            raise InvalidHttpEndpointDataError(f'Invalid scheme: {value}')
        return value


class HttpEndpointProviderCharmEvents(CharmEvents):
    """Custom events for HttpEndpointRequirer."""

    http_endpoint_config_changed = EventSource(EventBase)
    http_endpoint_config_required = EventSource(EventBase)


class HttpEndpointProvider(Object):
    """The http_endpoint interface provider."""

    on = HttpEndpointProviderCharmEvents()  # type: ignore[reportAssignmentType]

    def __init__(self, charm: CharmBase, relation_name: str) -> None:
        """Initialize an instance of HttpEndpointProvider class.

        Args:
            charm: The charm instance.
            relation_name: The name of relation.
            scheme: The scheme for the endpoint.
            listen_port: The port on which the endpoint is listening.
        """
        super().__init__(charm, relation_name)

        self.charm = charm
        self.relation_name = relation_name

        self.scheme: str | None = None
        self.listen_port: int | None = None

        self.framework.observe(charm.on[relation_name].relation_broken, self._configure)
        self.framework.observe(charm.on[relation_name].relation_changed, self._configure)
        self.framework.observe(self.on.http_endpoint_config_changed, self._configure)

    def _configure(self, _: EventBase) -> None:
        """Configure the provider side of http_endpoint interface idempotently.

        This method sets the HTTP endpoint information of the leader unit in the relation
        application data bag.
        """
        if not self.charm.unit.is_leader():
            logger.debug('Only leader unit can set http endpoint information')
            return

        relations = self.charm.model.relations[self.relation_name]
        if not relations:
            logger.debug('No %s relations found', self.relation_name)
            return

        # Get the leader"s address
        binding = self.charm.model.get_binding(self.relation_name)
        if not binding:
            logger.warning('Could not determine ingress address for http endpoint relation')
            return

        ingress_address = binding.network.ingress_address
        if not ingress_address:
            logger.warning(
                'Relation data (%s) is not ready: missing ingress address', self.relation_name
            )
            return

        if not self.scheme or not self.listen_port:
            logger.warning(
                'HTTP endpoint configuration is incomplete: scheme=%s, listen_port=%s',
                self.scheme,
                self.listen_port,
            )
            self.on.http_endpoint_config_required.emit()
            return

        http_endpoint = HttpEndpointDataModel(
            scheme=self.scheme,
            port=str(self.listen_port),  # convert to str
            hostname=str(ingress_address),
        )

        # Publish the HTTP endpoint to all relations" application data bags
        for relation in relations:
            relation_data = relation.data[self.charm.app]
            relation_data.update(http_endpoint.model_dump())
            logger.info('Published HTTP output URL to relation %s: %s', relation.id, http_endpoint)

        self.charm.unit.set_ports(self.listen_port)

    def update_config(self, scheme: str, listen_port: int) -> None:
        """Update http endpoint configuration.

        Args:
            scheme: The scheme to use (only http or https).
            listen_port: The listen port to open [1, 65535].

        Raises:
            InvalidHttpEndpointDataError if not valid scheme.
        """
        self.scheme = scheme
        self.listen_port = listen_port
        self.on.http_endpoint_config_changed.emit()


class HttpEndpointRequirerCharmEvents(CharmEvents):
    """Custom events for HttpEndpointRequirer."""

    http_endpoint_available = EventSource(EventBase)
    http_endpoint_unavailable = EventSource(EventBase)


class HttpEndpointRequirer(Object):
    """The http_endpoint interface requirer."""

    on = HttpEndpointRequirerCharmEvents()  # type: ignore[reportAssignmentType]

    def __init__(self, charm: CharmBase, relation_name: str) -> None:
        """Initialize an instance of HttpEndpointRequirer class.

        Args:
            charm: charm instance.
            relation_name: http_endpoint relation name.
        """
        super().__init__(charm, relation_name)

        self.charm = charm
        self.relation_name = relation_name

        self._http_endpoints: list[HttpEndpointDataModel] = []

        self.framework.observe(charm.on[relation_name].relation_broken, self._configure)
        self.framework.observe(charm.on[relation_name].relation_changed, self._configure)

    @property
    def http_endpoints(self) -> list[HttpEndpointDataModel]:
        """The list of HTTP endpoints of the leader units retrieved from the relation.

        Returns:
            An instance of HttpEndpointDataModel containing the HTTP endpoint data if available.
        """
        return self._http_endpoints

    def _configure(self, _: EventBase) -> None:
        """Configure the requirer side of http_endpoint interface idempotently.

        This method retrieves and validates the HTTP endpoint data from the relation. The retrieved
        data will be stored in the `http_endpoint` attribute if valid.
        """
        relations = self.charm.model.relations[self.relation_name]
        if not relations:
            logger.debug('No %s relations found', self.relation_name)
            self.on.http_endpoint_unavailable.emit()
            return None

        for relation in relations:
            data = relation.data.get(relation.app)
            if not data:
                logger.warning('Relation data (%s) is not ready', self.relation_name)
                continue
            self._http_endpoints.append(
                HttpEndpointDataModel(
                    port=data['port'],
                    scheme=data['scheme'],
                    hostname=data['hostname'],
                )
            )
            logger.info('Retrieved HTTP output info from relation %s: %s', relation.id, data)

        if self.http_endpoints:
            self.on.http_endpoint_available.emit()
        else:
            self.on.http_endpoint_unavailable.emit()
