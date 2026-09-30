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


"""Interface library for providing API Gateways with Identity and Access Proxy information.

It is required to integrate with OAuth2 Proxy - a reverse proxy and static file server that provides authentication
using Identity Platform's built-in identity management system and integrated identity providers (Google, GitHub, and others).

Migrated from charms.oauth2_proxy_k8s.v0.forward_auth (v0.2).

Version: 1.0.0
"""

import inspect
import json
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import jsonschema
from ops.charm import CharmBase, RelationBrokenEvent, RelationChangedEvent, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Handle, Object, ObjectEvents
from ops.model import TooManyRelatedAppsError

RELATION_NAME = 'forward-auth'
INTERFACE_NAME = 'forward_auth'

logger = logging.getLogger(__name__)


FORWARD_AUTH_PROVIDER_JSON_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema',
    '$id': 'https://canonical.github.io/charm-relation-interfaces/docs/json_schemas/forward_auth/v0/provider.json',
    'type': 'object',
    'properties': {
        'decisions_address': {'type': 'string', 'default': None},
        'app_names': {'type': 'array', 'default': None, 'items': {'type': 'string'}},
        'headers': {'type': 'array', 'default': None, 'items': {'type': 'string'}},
    },
    'required': ['decisions_address', 'app_names'],
}

FORWARD_AUTH_REQUIRER_JSON_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema',
    '$id': 'https://canonical.github.io/charm-relation-interfaces/docs/json_schemas/forward_auth/v0/requirer.json',
    'type': 'object',
    'properties': {
        'ingress_app_names': {'type': 'array', 'default': None, 'items': {'type': 'string'}},
    },
    'required': ['ingress_app_names'],
}


class ForwardAuthConfigError(Exception):
    """Emitted when invalid forward auth config is provided."""


class DataValidationError(RuntimeError):
    """Raised when data validation fails on relation data."""


def _load_data(data: Mapping[str, str], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parses nested fields and checks whether `data` matches `schema`."""
    ret: dict[str, Any] = {}
    for k, v in data.items():
        try:
            ret[k] = json.loads(v)
        except json.JSONDecodeError:
            ret[k] = v

    if schema:
        _validate_data(ret, schema)
    return ret


def _dump_data(
    data: dict[str, list[Any] | str], schema: dict[str, Any] | None = None
) -> dict[str, str]:
    if schema:
        _validate_data(data, schema)

    ret: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            try:
                ret[k] = json.dumps(v)
            except json.JSONDecodeError as e:
                raise DataValidationError(f'Failed to encode relation json: {e}')
        else:
            ret[k] = v
    return ret


class ForwardAuthRelation(Object):
    """A class containing helper methods for forward-auth relation."""

    _relation_name: str

    def _pop_relation_data(self, relation_id: int) -> None:
        if not self.model.unit.is_leader():
            return

        if len(self.model.relations) == 0:
            return

        relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        if not relation or not relation.app:
            return

        try:
            for data in list(relation.data[self.model.app]):
                relation.data[self.model.app].pop(data, '')
        except Exception as e:
            logger.info(f'Failed to pop the relation data: {e}')


def _validate_data(data: dict[str, Any], schema: dict[str, Any]) -> None:
    """Checks whether `data` matches `schema`.

    Will raise DataValidationError if the data is not valid, else return None.
    """
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise DataValidationError(data, schema) from e


@dataclass
class ForwardAuthConfig:
    """Helper class containing configuration required by API Gateway to set up the proxy."""

    decisions_address: str
    app_names: list[str]
    headers: list[str] = field(default_factory=lambda: [])

    @classmethod
    def from_dict(cls, dic: dict[str, Any]) -> 'ForwardAuthConfig':
        """Generate ForwardAuthConfig instance from dict."""
        return cls(**{k: v for k, v in dic.items() if k in inspect.signature(cls).parameters})

    def to_dict(self) -> dict[str, Any]:
        """Convert object to dict."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ForwardAuthRequirerConfig:
    """Helper class containing configuration required by OAuth2 Proxy.

    Its purpose is to evaluate whether apps can be protected by IAP.
    """

    ingress_app_names: list[str] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        self.ingress_app_names = list(dict.fromkeys(self.ingress_app_names))

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


class AuthConfigChangedEvent(EventBase):
    """Event to notify the requirer charm that the forward-auth config has changed."""

    def __init__(
        self,
        handle: Handle,
        decisions_address: str,
        app_names: list[str],
        headers: list[str],
        relation_id: int,
        relation_app_name: str,
    ) -> None:
        super().__init__(handle)
        self.decisions_address = decisions_address
        self.app_names = app_names
        self.headers = headers
        self.relation_id = relation_id
        self.relation_app_name = relation_app_name

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            'decisions_address': self.decisions_address,
            'app_names': self.app_names,
            'headers': self.headers,
            'relation_id': self.relation_id,
            'relation_app_name': self.relation_app_name,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.decisions_address = str(snapshot['decisions_address'])
        self.app_names = list(snapshot['app_names'])
        self.headers = list(snapshot['headers'])
        self.relation_id = int(snapshot['relation_id'])
        self.relation_app_name = str(snapshot['relation_app_name'])


class AuthConfigRemovedEvent(EventBase):
    """Event to notify the requirer charm that the forward-auth config was removed."""

    def __init__(
        self,
        handle: Handle,
        relation_id: int,
    ) -> None:
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {'relation_id': self.relation_id}

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.relation_id = int(snapshot['relation_id'])


class ForwardAuthRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `ForwardAuthRequirer`."""

    auth_config_changed = EventSource(AuthConfigChangedEvent)
    auth_config_removed = EventSource(AuthConfigRemovedEvent)


class ForwardAuthRequirer(ForwardAuthRelation):
    """Requirer side of the forward-auth relation."""

    on = ForwardAuthRequirerEvents()  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]

    def __init__(
        self,
        charm: CharmBase,
        *,
        relation_name: str = RELATION_NAME,
        ingress_app_names: ForwardAuthRequirerConfig | None = None,
    ) -> None:
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name
        self._ingress_app_names = ingress_app_names

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_relation_changed_event)
        self.framework.observe(events.relation_broken, self._on_relation_broken_event)

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Get the forward-auth config and emit a custom config-changed event."""
        if not self.model.unit.is_leader():
            return

        data = event.relation.data[event.app]
        if not data:
            logger.debug('No provider relation data available.')
            return

        try:
            forward_auth_data = _load_data(data, FORWARD_AUTH_PROVIDER_JSON_SCHEMA)
        except DataValidationError as e:
            logger.error(
                f'Received invalid config from the provider: {e}. Config-changed will not be emitted.'
            )
            return

        decisions_address = forward_auth_data.get('decisions_address')
        app_names: list[str] = forward_auth_data.get('app_names') or []
        headers: list[str] = forward_auth_data.get('headers') or []

        relation_id = event.relation.id
        relation_app_name = event.relation.app.name

        # Notify Traefik to update the routes
        self.on.auth_config_changed.emit(
            decisions_address, app_names, headers, relation_id, relation_app_name
        )

    def _on_relation_broken_event(self, event: RelationBrokenEvent) -> None:
        """Notify the requirer that the relation was broken."""
        self.on.auth_config_removed.emit(event.relation.id)

    def update_requirer_relation_data(
        self,
        ingress_app_names: ForwardAuthRequirerConfig | None,
        relation_id: int | None = None,
    ) -> None:
        """Update the relation databag with app names that can get IAP protection."""
        if not self.model.unit.is_leader():
            return

        if not ingress_app_names:
            logger.error('Ingress-related app names are missing')
            return

        if not isinstance(ingress_app_names, ForwardAuthRequirerConfig):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f'Unexpected type: {type(ingress_app_names)}')

        try:
            relation = self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        except TooManyRelatedAppsError:
            raise TooManyRelatedAppsError(  # pyright: ignore[reportCallIssue]
                'More than one relation is defined. Please provide a relation_id'
            )

        if not relation or not relation.app:
            return

        data = _dump_data(ingress_app_names.to_dict(), FORWARD_AUTH_REQUIRER_JSON_SCHEMA)
        relation.data[self.model.app].update(data)

    def get_provider_info(self, relation_id: int | None = None) -> ForwardAuthConfig | None:
        """Get the provider information from the databag."""
        if len(self.model.relations) == 0:
            return None
        try:
            relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        except TooManyRelatedAppsError:
            raise TooManyRelatedAppsError(  # pyright: ignore[reportCallIssue]
                'More than one relation is defined. Please provide a relation_id'
            )
        if not relation or not relation.app:
            return None

        data = relation.data[relation.app]
        if not data:
            logger.debug('No relation data available.')
            return None

        data = _load_data(data, FORWARD_AUTH_PROVIDER_JSON_SCHEMA)
        forward_auth_config = ForwardAuthConfig.from_dict(data)
        logger.debug(f'ForwardAuthConfig: {forward_auth_config}')

        return forward_auth_config

    def get_remote_app_name(self, relation_id: int | None = None) -> str | None:
        """Get the remote app name."""
        if len(self.model.relations) == 0:
            return None
        try:
            relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        except TooManyRelatedAppsError:
            raise TooManyRelatedAppsError(  # pyright: ignore[reportCallIssue]
                'More than one relation is defined. Please provide a relation_id'
            )
        if not relation or not relation.app:
            return None

        return relation.app.name

    def is_ready(self, relation_id: int | None = None) -> bool | None:
        """Checks whether ForwardAuth is ready on this relation.

        Returns True when OAuth2 Proxy shared the config; False otherwise.
        """
        if len(self.model.relations) == 0:
            return None
        try:
            relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        except TooManyRelatedAppsError:
            raise TooManyRelatedAppsError(  # pyright: ignore[reportCallIssue]
                'More than one relation is defined. Please provide a relation_id'
            )

        if not relation or not relation.app:
            return None

        return (
            'decisions_address' in relation.data[relation.app]
            and 'app_names' in relation.data[relation.app]
        )

    def is_protected_app(self, app: str | None) -> bool:
        """Checks whether a given app requested to be protected by IAP."""
        if self.is_ready():
            forward_auth_config = self.get_provider_info()
            if forward_auth_config and app in forward_auth_config.app_names:
                return True
            return False

        return False


class ForwardAuthProxySet(EventBase):
    """Event to notify the charm that the proxy was set successfully."""

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {}

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        pass


class InvalidForwardAuthConfigEvent(EventBase):
    """Event to notify the charm that the forward-auth configuration is invalid."""

    def __init__(self, handle: Handle, error: str) -> None:
        super().__init__(handle)
        self.error = error

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            'error': self.error,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.error = str(snapshot['error'])


class ForwardAuthRelationRemovedEvent(EventBase):
    """Event to notify the charm that the relation was removed."""

    def __init__(
        self,
        handle: Handle,
        relation_id: int,
    ) -> None:
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {'relation_id': self.relation_id}

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.relation_id = int(snapshot['relation_id'])


class ForwardAuthProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `ForwardAuthProvider`."""

    forward_auth_proxy_set = EventSource(ForwardAuthProxySet)
    invalid_forward_auth_config = EventSource(InvalidForwardAuthConfigEvent)
    forward_auth_relation_removed = EventSource(ForwardAuthRelationRemovedEvent)


class ForwardAuthProvider(ForwardAuthRelation):
    """Provider side of the forward-auth relation."""

    on = ForwardAuthProviderEvents()  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = RELATION_NAME,
        forward_auth_config: ForwardAuthConfig | None = None,
    ) -> None:
        super().__init__(charm, relation_name)
        self.charm = charm
        self._relation_name = relation_name
        self.forward_auth_config = forward_auth_config

        events = self.charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created_event)
        self.framework.observe(events.relation_changed, self._on_relation_changed_event)
        self.framework.observe(events.relation_broken, self._on_relation_broken_event)

    def _on_relation_created_event(self, event: RelationCreatedEvent) -> None:
        """Update the relation with provider data when a relation is created."""
        if not self.model.unit.is_leader():
            return

        try:
            self._update_relation_data(self.forward_auth_config, event.relation.id)
        except ForwardAuthConfigError as e:
            self.on.invalid_forward_auth_config.emit(e.args[0])

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Update the relation with forward-auth config when a relation is changed."""
        if not self.model.unit.is_leader():
            return

        # Compare ingress-related apps with apps that requested the proxy
        self._compare_apps()

    def _on_relation_broken_event(self, event: RelationBrokenEvent) -> None:
        """Wipe the relation databag and notify the charm that the relation is broken."""
        # Workaround for https://github.com/canonical/operator/issues/888
        self._pop_relation_data(event.relation.id)

        self.on.forward_auth_relation_removed.emit(event.relation.id)

    def _compare_apps(self, relation_id: int | None = None) -> None:
        """Compare app names provided by OAuth2 Proxy with apps that are related via ingress.

        The ingress-related app names are provided by the relation requirer.
        If an app is not related via ingress-per-app/leader/unit,
        emit `InvalidForwardAuthConfigEvent`.
        If the app is related via ingress and thus eligible for IAP, emit `ForwardAuthProxySet`.
        """
        if len(self.model.relations) == 0:
            return None
        try:
            relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        except TooManyRelatedAppsError:
            raise TooManyRelatedAppsError(  # pyright: ignore[reportCallIssue]
                'More than one relation is defined. Please provide a relation_id'
            )
        if not relation or not relation.app:
            return None

        requirer_data = relation.data[relation.app]
        if not requirer_data:
            logger.info('No requirer relation data available.')
            return

        ingress_apps = requirer_data['ingress_app_names']

        for app in json.loads(relation.data[self.model.app]['app_names']):
            if app not in ingress_apps:
                self.on.invalid_forward_auth_config.emit(error=f'{app} is not related via ingress')
                return
            self.on.forward_auth_proxy_set.emit()

    def _update_relation_data(
        self, forward_auth_config: ForwardAuthConfig | None, relation_id: int | None = None
    ) -> None:
        """Validate the forward-auth config and update the relation databag."""
        if not self.model.unit.is_leader():
            return

        if not forward_auth_config:
            logger.info('Forward-auth config is missing')
            return

        if not isinstance(forward_auth_config, ForwardAuthConfig):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f'Unexpected forward_auth_config type: {type(forward_auth_config)}')

        try:
            relation = self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        except TooManyRelatedAppsError:
            raise TooManyRelatedAppsError(  # pyright: ignore[reportCallIssue]
                'More than one relation is defined. Please provide a relation_id'
            )

        if not relation or not relation.app:
            return

        data = _dump_data(forward_auth_config.to_dict(), FORWARD_AUTH_PROVIDER_JSON_SCHEMA)
        relation.data[self.model.app].update(data)

    def update_forward_auth_config(
        self, forward_auth_config: ForwardAuthConfig | None, relation_id: int | None = None
    ) -> None:
        """Update the forward-auth config stored in the object."""
        self._update_relation_data(forward_auth_config, relation_id=relation_id)
