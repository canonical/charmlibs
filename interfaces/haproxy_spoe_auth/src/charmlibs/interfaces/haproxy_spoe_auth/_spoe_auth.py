# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pylint: disable=duplicate-code
"""Source code for the spoe-auth interface library."""

import json
import logging
import re
from collections.abc import MutableMapping
from enum import StrEnum
from typing import Annotated, cast

from ops import CharmBase, RelationBrokenEvent
from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object
from ops.model import Relation
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, IPvAnyAddress, ValidationError

logger = logging.getLogger(__name__)
SPOE_AUTH_DEFAULT_RELATION_NAME = 'spoe-auth'
HAPROXY_CONFIG_INVALID_CHARACTERS = '\n\t#\\\'"\r$ '
# RFC-1034 and RFC-2181 compliance REGEX for validating FQDNs
HOSTNAME_REGEX = (
    r'(?=.{1,253})(?!.*--.*)(?:(?!-)(?![0-9])[a-zA-Z0-9-]'
    r'{1,63}(?<!-)\.){1,}(?:(?!-)[a-zA-Z0-9-]{1,63}(?<!-))'
)


def value_contains_invalid_characters(value: str) -> str:
    """Validate if value contains invalid haproxy config characters.

    Args:
        value: The value to validate.

    Raises:
        ValueError: When value contains invalid characters.

    Returns:
        The validated value.
    """
    if [char for char in value if char in HAPROXY_CONFIG_INVALID_CHARACTERS]:
        raise ValueError(f'Relation data contains invalid character(s) {value}')
    return value


def validate_hostname(value: str) -> str:
    """Validate if value is a valid hostname per RFC 1123.

    Args:
        value: The value to validate.

    Raises:
        ValueError: When value is not a valid hostname.

    Returns:
        The validated value.
    """
    if not re.match(HOSTNAME_REGEX, value):
        raise ValueError(f'Invalid hostname: {value}')
    return value


VALIDSTR = Annotated[str, BeforeValidator(value_contains_invalid_characters)]


class DataValidationError(Exception):
    """Raised when data validation fails."""


class SpoeAuthInvalidRelationDataError(Exception):
    """Raised when data validation of the spoe-auth relation fails."""


class _DatabagModel(BaseModel):
    """Base databag model.

    Attrs:
        model_config: pydantic model configuration.
    """

    model_config = ConfigDict(
        # tolerate additional keys in databag
        extra='ignore',
        # Allow instantiating this class by field name (instead of forcing alias).
        populate_by_name=True,
        # Custom config key: whether to nest the whole datastructure (as json)
        # under a field or spread it out at the toplevel.
        _NEST_UNDER=None,
    )  # type: ignore
    """Pydantic config."""

    @classmethod
    def load(cls, databag: MutableMapping[str, str]) -> '_DatabagModel':
        """Load this model from a Juju json databag.

        Args:
            databag: Databag content.

        Raises:
            DataValidationError: When model validation failed.

        Returns:
            _DatabagModel: The validated model.
        """
        nest_under = cls.model_config.get('_NEST_UNDER')
        if nest_under:
            return cls.model_validate(json.loads(databag[nest_under]))

        try:
            data = {
                k: json.loads(v)
                for k, v in databag.items()
                # Don't attempt to parse model-external values
                if k in {(f.alias or n) for n, f in cls.model_fields.items()}
            }
        except json.JSONDecodeError as e:
            msg = f'invalid databag contents: expecting json. {databag}'
            logger.error(msg)
            raise DataValidationError(msg) from e

        try:
            return cls.model_validate_json(json.dumps(data))
        except ValidationError as e:
            msg = f'failed to validate databag: {databag}'
            logger.error(msg)
            raise DataValidationError(msg) from e

    def dump(
        self, databag: MutableMapping[str, str] | None = None, clear: bool = True
    ) -> MutableMapping[str, str] | None:
        """Write the contents of this model to Juju databag.

        Args:
            databag: The databag to write to.
            clear: Whether to clear the databag before writing.

        Returns:
            MutableMapping: The databag.
        """
        if clear and databag:
            databag.clear()

        if databag is None:
            databag = {}
        nest_under = self.model_config.get('_NEST_UNDER')
        if nest_under:
            databag[nest_under] = self.model_dump_json(
                by_alias=True,
            )
            return databag

        dct = self.model_dump(mode='json', by_alias=True)
        databag.update({k: json.dumps(v) for k, v in dct.items()})
        return databag


class HaproxyEvent(StrEnum):
    """Enumeration of HAProxy SPOE events.

    Attributes:
        ON_FRONTEND_HTTP_REQUEST: Event triggered on frontend HTTP request.
    """

    ON_FRONTEND_HTTP_REQUEST = 'on-frontend-http-request'


class SpoeAuthProviderAppData(_DatabagModel):
    """Configuration model for SPOE authentication provider.

    Attributes:
        spop_port: The port on the agent listening for SPOP.
        oidc_callback_port: The port on the agent handling OIDC callbacks.
        event: The event that triggers SPOE messages (e.g., on-http-request).
        var_authenticated: Name of the variable set by the SPOE agent for auth status.
        var_redirect_url: Name of the variable set by the SPOE agent for IDP redirect URL.
        cookie_name: Name of the authentication cookie used by the SPOE agent.
        oidc_callback_path: Path for OIDC callback.
        oidc_callback_hostname: The hostname HAProxy should route OIDC callbacks to.
    """

    spop_port: int = Field(
        description='The port on the agent listening for SPOP.',
        gt=0,
        le=65525,
    )
    oidc_callback_port: int = Field(
        description='The port on the agent handling OIDC callbacks.',
        gt=0,
        le=65525,
    )
    event: HaproxyEvent = Field(
        description='The event that triggers SPOE messages (e.g., on-http-request).',
    )
    var_authenticated: VALIDSTR = Field(
        description='Name of the variable set by the SPOE agent for auth status.',
    )
    var_redirect_url: VALIDSTR = Field(
        description='Name of the variable set by the SPOE agent for IDP redirect URL.',
    )
    cookie_name: VALIDSTR = Field(
        description='Name of the authentication cookie used by the SPOE agent.',
    )
    oidc_callback_path: VALIDSTR = Field(
        description='Path for OIDC callback.', default='/oauth2/callback'
    )
    oidc_callback_hostname: Annotated[str, BeforeValidator(validate_hostname)] = Field(
        description='The hostname HAProxy should route OIDC callbacks to.',
    )


class SpoeAuthProviderUnitData(_DatabagModel):
    """spoe-auth provider unit data.

    Attributes:
        address: IP address of the unit.
    """

    address: IPvAnyAddress = Field(description='IP address of the unit.')


class SpoeAuthProvider(Object):
    """SPOE auth interface provider implementation.

    Attributes:
        relations: Related applications.
    """

    def __init__(
        self, charm: CharmBase, relation_name: str = SPOE_AUTH_DEFAULT_RELATION_NAME
    ) -> None:
        """Initialize the SpoeAuthProvider.

        Args:
            charm: The charm that is instantiating the library.
            relation_name: The name of the relation to bind to.
        """
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

    @property
    def relations(self) -> list[Relation]:
        """The list of Relation instances associated with this relation_name.

        Returns:
            list[Relation]: The list of relations.
        """
        return list(self.charm.model.relations[self.relation_name])

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def provide_spoe_auth_requirements(
        self,
        relation: Relation,
        spop_port: int,
        oidc_callback_port: int,
        event: HaproxyEvent,
        var_authenticated: str,
        var_redirect_url: str,
        cookie_name: str,
        oidc_callback_hostname: str,
        oidc_callback_path: str = '/oauth2/callback',
        unit_address: str | None = None,
    ) -> None:
        """Set the SPOE auth configuration in the application databag.

        Args:
            relation: The relation instance to set data on.
            spop_port: The port on the agent listening for SPOP.
            oidc_callback_port: The port on the agent handling OIDC callbacks.
            event: The event that triggers SPOE messages.
            var_authenticated: Name of the variable for auth status.
            var_redirect_url: Name of the variable for IDP redirect URL.
            cookie_name: Name of the authentication cookie.
            oidc_callback_hostname: The hostname HAProxy should route OIDC callbacks to.
            oidc_callback_path: Path for OIDC callback.
            unit_address: The address of the unit.

        Raises:
            DataValidationError: When validation of application data fails.
        """
        if not self.charm.unit.is_leader():
            logger.warning('Only the leader unit can set the SPOE auth configuration.')
            return

        try:
            application_data = SpoeAuthProviderAppData(
                spop_port=spop_port,
                oidc_callback_port=oidc_callback_port,
                event=event,
                var_authenticated=var_authenticated,
                var_redirect_url=var_redirect_url,
                cookie_name=cookie_name,
                oidc_callback_hostname=oidc_callback_hostname,
                oidc_callback_path=oidc_callback_path,
            )
            unit_data = self._prepare_unit_data(unit_address)
        except ValidationError as exc:
            logger.error('Validation error when preparing provider relation data.')
            raise DataValidationError(
                'Validation error when preparing provider relation data.'
            ) from exc

        if self.charm.unit.is_leader():
            application_data.dump(relation.data[self.charm.app], clear=True)
        unit_data.dump(relation.data[self.charm.unit], clear=True)

    def _prepare_unit_data(self, unit_address: str | None) -> SpoeAuthProviderUnitData:
        """Prepare and validate unit data.

        Raises:
            DataValidationError: When no address or unit IP is available.

        Returns:
            RequirerUnitData: The validated unit data model.
        """
        if not unit_address:
            network_binding = self.charm.model.get_binding('juju-info')
            if (
                network_binding is not None
                and (bind_address := network_binding.network.bind_address) is not None
            ):
                unit_address = str(bind_address)
            else:
                logger.error('No unit IP available.')
                raise DataValidationError('No unit IP available.')
        return SpoeAuthProviderUnitData(address=cast('IPvAnyAddress', unit_address))


class SpoeAuthAvailableEvent(EventBase):
    """SpoeAuthAvailableEvent custom event."""


class SpoeAuthRemovedEvent(EventBase):
    """SpoeAuthRemovedEvent custom event."""


class SpoeAuthRequirerEvents(CharmEvents):
    """List of events that the SPOE auth requirer charm can leverage.

    Attributes:
        available: Emitted when provider configuration is available.
        removed: Emitted when the provider relation is broken.
    """

    available = EventSource(SpoeAuthAvailableEvent)
    removed = EventSource(SpoeAuthRemovedEvent)


class SpoeAuthRequirer(Object):
    """SPOE auth interface requirer implementation.

    Attributes:
        on: Custom events of the requirer.
        relation: The related application.
    """

    # Ignore this for pylance
    on = SpoeAuthRequirerEvents()  # type: ignore

    def __init__(
        self, charm: CharmBase, relation_name: str = SPOE_AUTH_DEFAULT_RELATION_NAME
    ) -> None:
        """Initialize the SpoeAuthRequirer.

        Args:
            charm: The charm that is instantiating the library.
            relation_name: The name of the relation to bind to.
        """
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

        self.framework.observe(self.charm.on[self.relation_name].relation_created, self._configure)
        self.framework.observe(self.charm.on[self.relation_name].relation_changed, self._configure)
        self.framework.observe(
            self.charm.on[self.relation_name].relation_broken, self._on_relation_broken
        )

    @property
    def relation(self) -> Relation | None:
        """The relation instance associated with this relation_name.

        Returns:
            Optional[Relation]: The relation instance, or None if not available.
        """
        relations = self.charm.model.relations[self.relation_name]
        return relations[0] if relations else None

    def _configure(self, _: EventBase) -> None:
        """Handle relation changed events."""
        if self.is_available():
            self.on.available.emit()

    def _on_relation_broken(self, _: RelationBrokenEvent) -> None:
        """Handle relation broken events."""
        self.on.removed.emit()

    def is_available(self) -> bool:
        """Check if the SPOE auth configuration is available and valid.

        Returns:
            bool: True if configuration is available and valid, False otherwise.
        """
        if not self.relation:
            return False

        if not self.relation.app:
            return False

        try:
            databag = self.relation.data[self.relation.app]
            if not databag:
                return False
            SpoeAuthProviderAppData.load(databag)
            return True
        except (DataValidationError, KeyError):
            return False

    def get_data(self) -> SpoeAuthProviderAppData | None:
        """Get the SPOE auth configuration from the provider.

        Returns:
            Optional[SpoeAuthProviderAppData]: The SPOE auth configuration,
                or None if not available.

        Raises:
            SpoeAuthInvalidRelationDataError: When configuration data is invalid.
        """
        if not self.relation:
            return None

        if not self.relation.app:
            return None

        try:
            databag = self.relation.data[self.relation.app]
            if not databag:
                return None
            return SpoeAuthProviderAppData.load(databag)  # type: ignore
        except DataValidationError as exc:
            logger.error(
                'spoe-auth data validation failed for relation %s: %s',
                self.relation,
                str(exc),
            )
            raise SpoeAuthInvalidRelationDataError(
                f'spoe-auth data validation failed for relation: {self.relation}'
            ) from exc

    def get_provider_unit_data(self, relation: Relation) -> list[SpoeAuthProviderUnitData]:
        """Fetch and validate the requirer's units data.

        Args:
            relation: The relation to fetch unit data from.

        Raises:
            DataValidationError: When unit data validation fails.

        Returns:
            list[SpoeAuthProviderUnitData]: List of validated unit data from the provider.
        """
        requirer_units_data: list[SpoeAuthProviderUnitData] = []

        for unit in relation.units:
            databag = relation.data.get(unit)
            if not databag:
                logger.error(
                    'Requirer unit data does not exist even though the unit is still present.'
                )
                continue
            try:
                data = cast('SpoeAuthProviderUnitData', SpoeAuthProviderUnitData.load(databag))
                requirer_units_data.append(data)
            except DataValidationError:
                logger.error('Invalid requirer application data for %s', unit)
                raise
        return requirer_units_data

    def get_provider_application_data(self, relation: Relation) -> SpoeAuthProviderAppData:
        """Fetch and validate the requirer's application databag.

        Args:
            relation: The relation to fetch application data from.

        Raises:
            DataValidationError: When requirer application data validation fails.

        Returns:
            RequirerApplicationData: Validated application data from the requirer.
        """
        try:
            return cast(
                'SpoeAuthProviderAppData',
                SpoeAuthProviderAppData.load(relation.data[relation.app]),
            )
        except DataValidationError:
            logger.error('Invalid requirer application data for %s', relation.app.name)
            raise
