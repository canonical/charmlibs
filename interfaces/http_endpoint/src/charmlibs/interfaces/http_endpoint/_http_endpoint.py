# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Source code of `charmlibs.interfaces.http_endpoint` v1.0.0."""

import json
import logging
from collections.abc import MutableMapping

from ops import CharmBase, CharmEvents, EventBase, EventSource, Object
from pydantic import BaseModel, HttpUrl, ValidationError

logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    """Exception raised for invalid data."""


class InvalidHttpEndpointDataError(Exception):
    """Exception raised for invalid http_endpoint data."""


class HttpEndpointDataModel(BaseModel):
    """Data model for http_endpoint interface."""

    url: HttpUrl

    def dump(self) -> MutableMapping[str, str]:
        """Output the contents of this model to be compatible with Juju databag.

        Returns:
            The databag as a string to string MutableMapping.
        """
        json_model = self.model_dump(mode='json')
        return {k: json.dumps(v) for k, v in json_model.items()}

    @classmethod
    def load(cls, databag: MutableMapping[str, str]) -> 'HttpEndpointDataModel':
        """Load this model from a Juju databag.

        Args:
            databag: The Juju databag to load from

        Return:
            An instance of this data model.
        """
        try:
            data = {k: json.loads(v) for k, v in databag.items()}
            data_model = cls.model_validate_json(json.dumps(data))
        except ValidationError as e:
            msg = f'failed to validate databag: {databag}'
            logger.error(msg)
            raise DataValidationError(msg) from e
        except json.JSONDecodeError as e:
            msg = f'invalid databag contents: expecting json. {databag}'
            logger.error(msg)
            raise DataValidationError(msg) from e

        return data_model


class HttpEndpointConfigChangedEvent(EventBase):
    """Event emitted when the http endpoint configuration is changed."""


class HttpEndpointProviderCharmEvents(CharmEvents):
    """Custom events for HttpEndpointProvider."""

    http_endpoint_config_changed = EventSource(HttpEndpointConfigChangedEvent)


class HttpEndpointProvider(Object):
    """The http_endpoint interface provider."""

    on = HttpEndpointProviderCharmEvents()  # type: ignore[reportAssignmentType]

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        path: str = '/',
        scheme: str = 'http',
        listen_port: int = 80,
    ) -> None:
        """Initialize an instance of HttpEndpointProvider class.

        Args:
            charm: The charm instance.
            relation_name: The name of relation.
            path: The url path.
            scheme: The scheme to use (only http or https).
            listen_port: The listen port to open [1, 65535].
        """
        super().__init__(charm, relation_name)

        self.charm = charm
        self.relation_name = relation_name

        self.path = path
        self.scheme = scheme
        self.listen_port = listen_port

        self.framework.observe(charm.on[relation_name].relation_broken, self._configure)
        self.framework.observe(charm.on[relation_name].relation_changed, self._configure)
        self.framework.observe(self.on.http_endpoint_config_changed, self._configure)
        self.framework.observe(charm.on.config_changed, self._configure)

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

        # Publish the HTTP endpoint to all relations" application data bags
        url = f'{self.scheme}://{ingress_address}:{self.listen_port}/{self.path.lstrip("/")}'
        try:
            http_endpoint = HttpEndpointDataModel(url=HttpUrl(url))
            for relation in relations:
                relation_data = relation.data[self.charm.app]
                relation_data.update(http_endpoint.dump())
                logger.info(
                    'Published HTTP endpoint to relation %s: %s', relation.id, http_endpoint
                )
        except (ValidationError, DataValidationError) as e:
            msg = f'Invalid http endpoint data: url={url}'
            logger.error(msg)
            raise InvalidHttpEndpointDataError(msg) from e

        self.charm.unit.set_ports(self.listen_port)

    def update_config(self, path: str, scheme: str, listen_port: int) -> None:
        """Update http endpoint configuration.

        Args:
            path: The url path.
            scheme: The scheme to use (only http or https).
            listen_port: The listen port to open [1, 65535].

        Raises:
            InvalidHttpEndpointDataError if not valid scheme.
        """
        self.path = path
        self.scheme = scheme
        self.listen_port = listen_port
        self.on.http_endpoint_config_changed.emit()


class HttpEndpointAvailableEvent(EventBase):
    """Event emitted when an HTTP endpoint becomes available."""


class HttpEndpointUnavailableEvent(EventBase):
    """Event emitted when an HTTP endpoint becomes unavailable."""


class HttpEndpointRequirerCharmEvents(CharmEvents):
    """Custom events for HttpEndpointRequirer."""

    http_endpoint_available = EventSource(HttpEndpointAvailableEvent)
    http_endpoint_unavailable = EventSource(HttpEndpointUnavailableEvent)


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

        self.framework.observe(charm.on[relation_name].relation_broken, self._configure)
        self.framework.observe(charm.on[relation_name].relation_changed, self._configure)
        self.framework.observe(charm.on.config_changed, self._configure)

    def get_http_endpoints(self) -> list[HttpEndpointDataModel]:
        """Get the list of HTTP endpoints of the leader units retrieved from the relation.

        Returns:
            An instance of HttpEndpointDataModel containing the HTTP endpoint data if available.
        """
        relations = self.charm.model.relations[self.relation_name]
        if not relations:
            logger.debug('No %s relations found', self.relation_name)
            return []

        http_endpoints: list[HttpEndpointDataModel] = []
        for relation in relations:
            data = relation.data.get(relation.app)
            if not data:
                logger.warning('Relation data (%s) is not ready', self.relation_name)
                continue
            http_endpoints.append(HttpEndpointDataModel.load(data))
            logger.info('Retrieved HTTP output info from relation %s: %s', relation.id, data)
        return http_endpoints

    def _configure(self, _: EventBase) -> None:
        """Configure the requirer side of http_endpoint interface idempotently.

        This method retrieves and validates the HTTP endpoint data from the relation. The retrieved
        data will be stored in the `http_endpoint` attribute if valid.
        """
        if self.get_http_endpoints():
            self.on.http_endpoint_available.emit()
        else:
            self.on.http_endpoint_unavailable.emit()
