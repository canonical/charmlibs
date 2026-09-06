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


"""OAuth interface implementation.

Migrated from charms.hydra.v0.oauth (v0.12).

Version: 1.0.0
"""

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from typing import Any, cast

import jsonschema
from ops.charm import CharmBase, RelationBrokenEvent, RelationChangedEvent, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Handle, Object, ObjectEvents
from ops.model import Relation, Secret, SecretNotFoundError, TooManyRelatedAppsError

logger = logging.getLogger(__name__)

DEFAULT_RELATION_NAME = 'oauth'
ALLOWED_GRANT_TYPES = [
    'authorization_code',
    'refresh_token',
    'client_credentials',
    'urn:ietf:params:oauth:grant-type:device_code',
]
ALLOWED_CLIENT_AUTHN_METHODS = ['client_secret_basic', 'client_secret_post']
CLIENT_SECRET_FIELD = 'secret'  # noqa: S105

url_regex = re.compile(
    r'(^http://)|(^https://)'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|'
    r'[A-Z0-9-]{2,}\.?)|'  # domain...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$',
    re.IGNORECASE,
)

OAUTH_PROVIDER_JSON_SCHEMA: dict[str, Any] = {
    '$schema': 'http://json-schema.org/draft-07/schema',
    '$id': 'https://canonical.github.io/charm-relation-interfaces/interfaces/oauth/schemas/provider.json',
    'type': 'object',
    'properties': {
        'issuer_url': {
            'type': 'string',
        },
        'authorization_endpoint': {
            'type': 'string',
        },
        'token_endpoint': {
            'type': 'string',
        },
        'introspection_endpoint': {
            'type': 'string',
        },
        'userinfo_endpoint': {
            'type': 'string',
        },
        'jwks_endpoint': {
            'type': 'string',
        },
        'scope': {
            'type': 'string',
        },
        'client_id': {
            'type': 'string',
        },
        'client_secret_id': {
            'type': 'string',
        },
        'groups': {'type': 'string', 'default': None},
        'ca_chain': {'type': 'array', 'items': {'type': 'string'}, 'default': []},
        'jwt_access_token': {'type': 'string', 'default': 'False'},
    },
    'required': [
        'issuer_url',
        'authorization_endpoint',
        'token_endpoint',
        'introspection_endpoint',
        'userinfo_endpoint',
        'jwks_endpoint',
        'scope',
    ],
}
OAUTH_REQUIRER_JSON_SCHEMA: dict[str, Any] = {
    '$schema': 'http://json-schema.org/draft-07/schema',
    '$id': 'https://canonical.github.io/charm-relation-interfaces/interfaces/oauth/schemas/requirer.json',
    'type': 'object',
    'properties': {
        'redirect_uri': {
            'type': 'string',
            'default': None,
        },
        'audience': {'type': 'array', 'default': [], 'items': {'type': 'string'}},
        'scope': {'type': 'string', 'default': None},
        'grant_types': {
            'type': 'array',
            'default': None,
            'items': {
                'enum': ALLOWED_GRANT_TYPES,
                'type': 'string',
            },
        },
        'token_endpoint_auth_method': {
            'type': 'string',
            'enum': ALLOWED_CLIENT_AUTHN_METHODS,
            'default': 'client_secret_basic',
        },
    },
    'required': ['audience', 'scope', 'grant_types', 'token_endpoint_auth_method'],
    'allOf': [
        {
            'if': {
                'properties': {
                    'grant_types': {
                        'contains': {
                            'const': 'authorization_code',
                        }
                    }
                },
                'required': ['grant_types'],
            },
            'then': {
                'required': ['redirect_uri'],
            },
        }
    ],
}


class ClientConfigError(Exception):
    """Emitted when invalid client config is provided."""


class DataValidationError(RuntimeError):
    """Raised when data validation fails on relation data."""


def _load_data(data: Mapping[str, str], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parses nested fields and checks whether `data` matches `schema`."""
    ret: dict[str, Any] = {}
    for k, v in data.items():
        try:
            ret[k] = json.loads(v)
        except json.JSONDecodeError:  # noqa: PERF203
            ret[k] = v

    if schema:
        _validate_data(ret, schema)
    return ret


def _dump_data(data: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, str]:
    if schema:
        _validate_data(data, schema)

    ret: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            try:
                ret[k] = json.dumps(v)
            except json.JSONDecodeError as e:
                raise DataValidationError(f'Failed to encode relation json: {e}') from e
        elif isinstance(v, bool):
            ret[k] = str(v)
        else:
            ret[k] = str(v)
    return ret


def strtobool(val: str) -> bool:
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    if not isinstance(val, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError(f'invalid value type {type(val)}')

    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    else:
        raise ValueError(f'invalid truth value {val}')


class OAuthRelation(Object):
    """A class containing helper methods for oauth relation."""

    _relation_name: str

    def _pop_relation_data(self, relation_id: Relation) -> None:
        if not self.model.unit.is_leader():
            return

        if len(self.model.relations) == 0:
            return

        relation = self.model.get_relation(self._relation_name, relation_id=relation_id.id)
        if not relation or not relation.app:
            return

        try:
            for data in list(relation.data[self.model.app]):
                relation.data[self.model.app].pop(data, '')
        except Exception as e:
            logger.info('Failed to pop the relation data: %s', e)


def _validate_data(data: dict[str, Any], schema: dict[str, Any]) -> None:
    """Checks whether `data` matches `schema`.

    Will raise DataValidationError if the data is not valid, else return None.
    """
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise DataValidationError(data, schema) from e


@dataclass
class ClientConfig:
    """Helper class containing a client's configuration."""

    redirect_uri: str | None
    scope: str
    grant_types: list[str]
    audience: list[str] = field(default_factory=lambda: [])
    token_endpoint_auth_method: str = 'client_secret_basic'  # noqa: S105
    client_id: str | None = None

    def validate(self) -> None:
        """Validate the client configuration."""
        if 'authorization_code' in self.grant_types and not self.redirect_uri:
            raise ClientConfigError(
                'redirect_uri is required when using authorization_code grant_type'
            )

        # Validate redirect_uri when configured
        if self.redirect_uri is not None and not re.match(url_regex, self.redirect_uri):
            raise ClientConfigError(f'Invalid URL {self.redirect_uri}')

        if self.redirect_uri is not None and self.redirect_uri.startswith('http://'):
            logger.warning("Provided Redirect URL uses http scheme. Don't do this in production")

        # Validate grant_types
        for grant_type in self.grant_types:
            if grant_type not in ALLOWED_GRANT_TYPES:
                raise ClientConfigError(
                    f'Invalid grant_type {grant_type}, must be one of {ALLOWED_GRANT_TYPES}'
                )

        # Validate client authentication methods
        if self.token_endpoint_auth_method not in ALLOWED_CLIENT_AUTHN_METHODS:
            raise ClientConfigError(
                f'Invalid client auth method {self.token_endpoint_auth_method}, '
                f'must be one of {ALLOWED_CLIENT_AUTHN_METHODS}'
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert object to dict."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class OauthProviderConfig:
    """Helper class containing provider's configuration."""

    issuer_url: str
    authorization_endpoint: str
    token_endpoint: str
    introspection_endpoint: str
    userinfo_endpoint: str
    jwks_endpoint: str
    scope: str
    client_id: str | None = None
    client_secret: str | None = None
    groups: str | None = None
    ca_chain: str | None = None
    jwt_access_token: bool | None = False

    @classmethod
    def from_dict(cls, dic: dict[str, Any]) -> 'OauthProviderConfig':
        """Generate OauthProviderConfig instance from dict."""
        jwt_access_token = False
        if 'jwt_access_token' in dic:
            val = dic['jwt_access_token']
            jwt_access_token = val if isinstance(val, bool) else strtobool(str(val))
        return cls(
            jwt_access_token=jwt_access_token,
            **{
                k: v
                for k, v in dic.items()
                if k in [f.name for f in fields(cls)] and k != 'jwt_access_token'
            },
        )


class OAuthInfoChangedEvent(EventBase):
    """Event to notify the charm that the information in the databag changed."""

    def __init__(self, handle: Handle, client_id: str, client_secret_id: str):
        super().__init__(handle)
        self.client_id = client_id
        self.client_secret_id = client_secret_id

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            'client_id': self.client_id,
            'client_secret_id': self.client_secret_id,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        super().restore(snapshot)
        self.client_id = cast('str', snapshot['client_id'])
        self.client_secret_id = cast('str', snapshot['client_secret_id'])


class InvalidClientConfigEvent(EventBase):
    """Event to notify the charm that the client configuration is invalid."""

    def __init__(self, handle: Handle, error: str):
        super().__init__(handle)
        self.error = error

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            'error': self.error,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.error = cast('str', snapshot['error'])


class OAuthInfoRemovedEvent(EventBase):
    """Event to notify the charm that the provider data was removed."""

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {}

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        pass


class OAuthRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `OAuthRequirerEvents`."""

    oauth_info_changed = EventSource(OAuthInfoChangedEvent)
    oauth_info_removed = EventSource(OAuthInfoRemovedEvent)
    invalid_client_config = EventSource(InvalidClientConfigEvent)


class OAuthRequirer(OAuthRelation):
    """Register an oauth client."""

    on = OAuthRequirerEvents()  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]

    def __init__(
        self,
        charm: CharmBase,
        client_config: ClientConfig | None = None,
        relation_name: str = DEFAULT_RELATION_NAME,
    ) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._client_config = client_config
        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created_event)
        self.framework.observe(events.relation_changed, self._on_relation_changed_event)
        self.framework.observe(events.relation_broken, self._on_relation_broken_event)

    def _on_relation_created_event(self, event: RelationCreatedEvent) -> None:
        try:
            self._update_relation_data(self._client_config, event.relation.id)
        except ClientConfigError as e:
            self.on.invalid_client_config.emit(e.args[0])

    def _on_relation_broken_event(self, event: RelationBrokenEvent) -> None:
        # This may be caused by a provider unit being removed.
        # Also the oauth data may still be there, perhaps we should remove this
        # event altogether for now.

        # Notify the requirer that the relation data was removed
        self.on.oauth_info_removed.emit()

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        if not event.app:
            return
        raw_data = cast('Mapping[str, str]', event.relation.data.get(event.app))
        if not raw_data:
            logger.info('No relation data available.')
            return

        data = _load_data(raw_data, OAUTH_PROVIDER_JSON_SCHEMA)

        client_id = cast('str | None', data.get('client_id'))
        client_secret_id = cast('str | None', data.get('client_secret_id'))
        if not client_id or not client_secret_id:
            logger.info('OAuth Provider info is available, waiting for client to be registered.')
            # The client credentials are not ready yet, so we do nothing
            # This could mean that the client credentials were removed from the databag,
            # but we don't allow that (for now), so we don't have to check for it.
            return

        self.on.oauth_info_changed.emit(client_id, client_secret_id)

    def _update_relation_data(
        self, client_config: ClientConfig | None, relation_id: int | None = None
    ) -> None:
        if not self.model.unit.is_leader() or not client_config:
            return

        if not isinstance(client_config, ClientConfig):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError(f'Unexpected client_config type: {type(client_config)}')

        client_config.validate()

        try:
            relation = self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        except TooManyRelatedAppsError as e:
            raise RuntimeError(
                'More than one relations are defined. Please provide a relation_id'
            ) from e

        if not relation or not relation.app:
            return

        data = _dump_data(client_config.to_dict(), OAUTH_REQUIRER_JSON_SCHEMA)
        relation.data[self.model.app].update(data)

    def is_client_created(self, relation_id: int | None = None) -> bool | None:
        """Check if the client has been created."""
        if len(self.model.relations) == 0:
            return None
        try:
            relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        except TooManyRelatedAppsError as e:
            raise RuntimeError(
                'More than one relations are defined. Please provide a relation_id'
            ) from e

        if not relation or not relation.app:
            return None

        return (
            'client_id' in relation.data[relation.app]
            and 'client_secret_id' in relation.data[relation.app]
        )

    def get_provider_info(self, relation_id: int | None = None) -> OauthProviderConfig | None:
        """Get the provider information from the databag."""
        if len(self.model.relations) == 0:
            return None
        try:
            relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        except TooManyRelatedAppsError as e:
            raise RuntimeError(
                'More than one relations are defined. Please provide a relation_id'
            ) from e
        if not relation or not relation.app:
            return None

        raw_data = relation.data.get(relation.app)
        if not raw_data:
            logger.info('No relation data available.')
            return

        data = _load_data(raw_data, OAUTH_PROVIDER_JSON_SCHEMA)

        client_secret_id = cast('str | None', data.get('client_secret_id'))
        if client_secret_id:
            client_secret_obj = self.get_client_secret(client_secret_id)
            client_secret = client_secret_obj.get_content()[CLIENT_SECRET_FIELD]
            data['client_secret'] = client_secret

        oauth_provider = OauthProviderConfig.from_dict(data)
        return oauth_provider

    def get_client_secret(self, client_secret_id: str) -> Secret:
        """Get the client_secret."""
        client_secret = self.model.get_secret(id=client_secret_id)
        return client_secret

    def update_client_config(
        self, client_config: ClientConfig, relation_id: int | None = None
    ) -> None:
        """Update the client config stored in the object."""
        self._client_config = client_config
        self._update_relation_data(client_config, relation_id=relation_id)


class ClientCreatedEvent(EventBase):
    """Event to notify the Provider charm to create a new client."""

    def __init__(
        self,
        handle: Handle,
        redirect_uri: str,
        scope: str,
        grant_types: list[str],
        audience: list[str],
        token_endpoint_auth_method: str,
        relation_id: int,
    ) -> None:
        super().__init__(handle)
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.grant_types = grant_types
        self.audience = audience
        self.token_endpoint_auth_method = token_endpoint_auth_method
        self.relation_id = relation_id

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'grant_types': self.grant_types,
            'audience': self.audience,
            'token_endpoint_auth_method': self.token_endpoint_auth_method,
            'relation_id': self.relation_id,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.redirect_uri = cast('str', snapshot['redirect_uri'])
        self.scope = cast('str', snapshot['scope'])
        self.grant_types = cast('list[str]', snapshot['grant_types'])
        self.audience = cast('list[str]', snapshot['audience'])
        self.token_endpoint_auth_method = cast('str', snapshot['token_endpoint_auth_method'])
        self.relation_id = cast('int', snapshot['relation_id'])

    def to_client_config(self) -> ClientConfig:
        """Convert the event information to a ClientConfig object."""
        return ClientConfig(
            self.redirect_uri,
            self.scope,
            self.grant_types,
            self.audience,
            self.token_endpoint_auth_method,
        )


class ClientChangedEvent(EventBase):
    """Event to notify the Provider charm that the client config changed."""

    def __init__(
        self,
        handle: Handle,
        redirect_uri: str,
        scope: str,
        grant_types: list[str],
        audience: list[str],
        token_endpoint_auth_method: str,
        relation_id: int,
        client_id: str,
    ) -> None:
        super().__init__(handle)
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.grant_types = grant_types
        self.audience = audience
        self.token_endpoint_auth_method = token_endpoint_auth_method
        self.relation_id = relation_id
        self.client_id = client_id

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'grant_types': self.grant_types,
            'audience': self.audience,
            'token_endpoint_auth_method': self.token_endpoint_auth_method,
            'relation_id': self.relation_id,
            'client_id': self.client_id,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.redirect_uri = cast('str', snapshot['redirect_uri'])
        self.scope = cast('str', snapshot['scope'])
        self.grant_types = cast('list[str]', snapshot['grant_types'])
        self.audience = cast('list[str]', snapshot['audience'])
        self.token_endpoint_auth_method = cast('str', snapshot['token_endpoint_auth_method'])
        self.relation_id = cast('int', snapshot['relation_id'])
        self.client_id = cast('str', snapshot['client_id'])

    def to_client_config(self) -> ClientConfig:
        """Convert the event information to a ClientConfig object."""
        return ClientConfig(
            self.redirect_uri,
            self.scope,
            self.grant_types,
            self.audience,
            self.token_endpoint_auth_method,
            self.client_id,
        )


class ClientDeletedEvent(EventBase):
    """Event to notify the Provider charm that the client was deleted."""

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
        self.relation_id = cast('int', snapshot['relation_id'])


class OAuthProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `OAuthProviderEvents`."""

    client_created = EventSource(ClientCreatedEvent)
    client_changed = EventSource(ClientChangedEvent)
    client_deleted = EventSource(ClientDeletedEvent)


class OAuthProvider(OAuthRelation):
    """A provider object for OIDC Providers."""

    on = OAuthProviderEvents()  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]

    def __init__(self, charm: CharmBase, relation_name: str = DEFAULT_RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_changed,
            self._get_client_config_from_relation_data,
        )
        self.framework.observe(
            events.relation_broken,
            self._on_relation_broken,
        )

    def _get_client_config_from_relation_data(self, event: RelationChangedEvent) -> None:
        if not self.model.unit.is_leader():
            return

        if not event.app:
            return

        raw_data = cast('Mapping[str, str]', event.relation.data.get(event.app))
        if not raw_data:
            logger.info('No requirer relation data available.')
            return

        client_data = _load_data(raw_data, OAUTH_REQUIRER_JSON_SCHEMA)
        redirect_uri = cast('str | None', client_data.get('redirect_uri'))
        scope = cast('str | None', client_data.get('scope'))
        grant_types = cast('list[str] | None', client_data.get('grant_types'))
        audience = cast('list[str] | None', client_data.get('audience'))
        token_endpoint_auth_method = cast(
            'str | None', client_data.get('token_endpoint_auth_method')
        )

        provider_data_raw = cast('Mapping[str, str]', event.relation.data.get(self._charm.app))
        if not provider_data_raw:
            logger.info('No provider relation data available.')
            return
        provider_data = _load_data(provider_data_raw, OAUTH_PROVIDER_JSON_SCHEMA)
        client_id = cast('str | None', provider_data.get('client_id'))

        relation_id = event.relation.id

        if client_id:
            # Modify an existing client
            self.on.client_changed.emit(
                redirect_uri,
                scope,
                grant_types,
                audience,
                token_endpoint_auth_method,
                relation_id,
                client_id,
            )
        else:
            # Create a new client
            self.on.client_created.emit(
                redirect_uri, scope, grant_types, audience, token_endpoint_auth_method, relation_id
            )

    def _get_secret_label(self, relation: Relation) -> str:
        return f'client_secret_{relation.id}'

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        # There is no way to tell if this event was emitted because the
        # relation was removed or if one of the applications was scaled down.
        # Until this is fixed, we don't delete the client.
        # Workaround for https://github.com/canonical/operator/issues/888
        # self._pop_relation_data(event.relation.id)

        # self._delete_juju_secret(event.relation)
        self.on.client_deleted.emit(event.relation.id)

    def _create_juju_secret(self, client_secret: str, relation: Relation) -> Secret:
        """Create a juju secret and grant it to a relation."""
        secret = {CLIENT_SECRET_FIELD: client_secret}
        juju_secret = self.model.app.add_secret(secret, label=self._get_secret_label(relation))
        juju_secret.grant(relation)
        return juju_secret

    def _delete_juju_secret(self, relation: Relation) -> None:
        try:
            secret = self.model.get_secret(label=self._get_secret_label(relation))
        except SecretNotFoundError:
            return
        else:
            secret.remove_all_revisions()

    def remove_secret(self, relation: Relation) -> None:
        return self._delete_juju_secret(relation)

    def set_provider_info_in_relation_data(
        self,
        issuer_url: str,
        authorization_endpoint: str,
        token_endpoint: str,
        introspection_endpoint: str,
        userinfo_endpoint: str,
        jwks_endpoint: str,
        scope: str,
        groups: str | None = None,
        ca_chain: str | None = None,
        jwt_access_token: bool | None = False,
    ) -> None:
        """Put the provider information in the databag."""
        if not self.model.unit.is_leader():
            return

        data = {
            'issuer_url': issuer_url,
            'authorization_endpoint': authorization_endpoint,
            'token_endpoint': token_endpoint,
            'introspection_endpoint': introspection_endpoint,
            'userinfo_endpoint': userinfo_endpoint,
            'jwks_endpoint': jwks_endpoint,
            'scope': scope,
            'jwt_access_token': jwt_access_token,
        }
        if groups:
            data['groups'] = groups
        if ca_chain:
            data['ca_chain'] = ca_chain

        for relation in self.model.relations[self._relation_name]:
            relation.data[self.model.app].update(_dump_data(data))

    def set_client_credentials_in_relation_data(
        self, relation_id: int, client_id: str, client_secret: str
    ) -> None:
        """Put the client credentials in the databag."""
        if not self.model.unit.is_leader():
            return

        relation = self.model.get_relation(self._relation_name, relation_id)
        if not relation or not relation.app:
            return
        # TODO: What if we are refreshing the client_secret? We need to add a
        # new revision for that
        secret = self._create_juju_secret(client_secret, relation)
        data = {'client_id': client_id, 'client_secret_id': secret.id}
        relation.data[self.model.app].update(_dump_data(data))
