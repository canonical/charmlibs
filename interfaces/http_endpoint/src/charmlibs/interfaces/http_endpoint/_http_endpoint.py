# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Source code of `charmlibs.interfaces.http_endpoint` v1.0.0."""

import logging

from ops import CharmBase, EventBase, Object
from pydantic import BaseModel, HttpUrl, ValidationError

logger = logging.getLogger(__name__)


class _HttpEndpointDataModel(BaseModel):
    """Data model for http_endpoint interface."""

    url: HttpUrl


class HttpEndpointInvalidDataError(Exception):
    """Exception raised for invalid http_endpoint data."""


class HttpEndpointProvider(Object):
    """The http_endpoint interface provider."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        path: str = '/',
        scheme: str = 'http',
        listen_port: int = 80,
        set_ports: bool = False,
    ) -> None:
        """Initialize an instance of HttpEndpointProvider class.

        The provider side of the http_endpoint interface publishes the HTTP endpoint information of
        the leader unit in the relation application data bag. The provider can be initialized with
        custom parameters (path, scheme, listen_port) if they are known in advanced. By default,
        the endpoint will be assumed to be at the root path "/" using the "http" scheme on port 80.
        Alternatively, if the scheme and port are not known at the beginning or depend on other
        factors (e.g. config option or certificate relation), the provider can updated those
        parameters later via `update_config` method.

        The provider can also optionally set the port on the unit if specified, but the charm
        author is responsible for ensuring that the related unit is able communicate over that
        port.

        Args:
            charm: The charm instance.
            relation_name: The name of relation.
            path: The url path.
            scheme: The scheme to use (only http or https).
            listen_port: The listen port to open [1, 65535].
            set_ports: Whether to set the unit port on the charm.
        """
        super().__init__(charm, relation_name)

        self.charm = charm
        self.relation_name = relation_name
        self.path = path
        self.scheme = scheme
        self.listen_port = listen_port
        self.set_ports = set_ports

        self.framework.observe(charm.on[relation_name].relation_changed, self._configure)
        self.framework.observe(charm.on.config_changed, self._configure)

    def _configure(self, _: EventBase) -> None:
        """Configure the provider side of http_endpoint interface idempotently."""
        self._update_config()

    def _update_config(self) -> None:
        """Update the provider side of http_endpoint interface idempotently.

        This method sets the HTTP endpoint information of the leader unit in the relation
        application data bag.
        """
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

        url = f'{self.scheme}://{ingress_address}:{self.listen_port}/{self.path.lstrip("/")}'
        try:
            http_endpoint = _HttpEndpointDataModel(url=HttpUrl(url))
            for relation in relations:
                relation.save(http_endpoint, self.charm.unit)
                if self.charm.unit.is_leader():
                    relation.save(http_endpoint, self.charm.app)
                logger.info(
                    'Published HTTP endpoint to relation %s: %s', relation.id, http_endpoint
                )
        except ValidationError as e:
            msg = f'Invalid http endpoint data: url={url}'
            logger.error(msg)
            raise HttpEndpointInvalidDataError(msg) from e

        if self.set_ports:
            self.charm.unit.set_ports(self.listen_port)

    def update_config(
        self, path: str, scheme: str, listen_port: int, set_ports: bool = False
    ) -> None:
        """Update http endpoint configuration.

        Args:
            path: The url path.
            scheme: The scheme to use (only http or https).
            listen_port: The listen port to open [1, 65535].
            set_ports: Whether to set the unit ports on the charm.

        Raises:
            HttpEndpointInvalidDataError if not valid scheme.
        """
        self.path = path
        self.scheme = scheme
        self.listen_port = listen_port
        self.set_ports = set_ports
        self._update_config()


class HttpEndpointRequirer(Object):
    """The http_endpoint interface requirer."""

    def __init__(self, charm: CharmBase, relation_name: str) -> None:
        """Initialize an instance of HttpEndpointRequirer class.

        Args:
            charm: charm instance.
            relation_name: http_endpoint relation name.
        """
        super().__init__(charm, relation_name)

        self.charm = charm
        self.relation_name = relation_name

    def get_urls(self) -> dict[str, str]:
        """Get the list of urls from HTTP endpoints of the from all related units.

        Returns:
            A dictionary of unit names to URLs from the HTTP endpoints of all related units if
            available.
        """
        relations = self.charm.model.relations[self.relation_name]
        if not relations:
            logger.debug('No %s relations found', self.relation_name)
            return {}

        http_endpoints: dict[str, str] = {}
        for relation in relations:
            for unit in relation.units:
                if unit not in relation.data and not relation.data.get(unit):
                    logger.warning('Relation data (%s) is not ready', self.relation_name)
                    continue
                try:
                    data = relation.load(_HttpEndpointDataModel, unit)
                    http_endpoints[unit.name] = str(data.url)
                    logger.info('Retrieved URL from relation %s: %s', relation.id, data)
                except ValidationError as e:
                    logger.error('Invalid URL endpoint data in relation %s: %s', relation.id, e)
        return http_endpoints

    def get_leader_urls(self) -> list[str]:
        """Get the list of urls from HTTP endpoints of the leader units.

        Returns:
            A list of URLs from the HTTP endpoints of the leader units if available.
        """
        relations = self.charm.model.relations[self.relation_name]
        if not relations:
            logger.debug('No %s relations found', self.relation_name)
            return []

        http_endpoints: list[str] = []
        for relation in relations:
            if relation.app not in relation.data and not relation.data.get(relation.app):
                logger.warning('Relation data (%s) is not ready', self.relation_name)
                continue
            try:
                data = relation.load(_HttpEndpointDataModel, relation.app)
                http_endpoints.append(str(data.url))
                logger.info('Retrieved URL from relation %s: %s', relation.id, data)
            except ValidationError as e:
                logger.error('Invalid URL endpoint data in relation %s: %s', relation.id, e)
        return http_endpoints
