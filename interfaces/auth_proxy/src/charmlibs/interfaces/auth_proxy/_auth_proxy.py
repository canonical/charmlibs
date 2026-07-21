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

"""Interface library for providing OAuth2 Proxy with downstream charms' auth-proxy information.

It is required to integrate a charm into an Identity and Access Proxy (IAP).

Migrated from charms.oauth2_proxy_k8s.v0.auth_proxy (v0.4).

Version: 1.0.0
"""

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, cast

import jsonschema
from ops.charm import CharmBase, RelationBrokenEvent, RelationChangedEvent, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Handle, Object, ObjectEvents
from ops.model import TooManyRelatedAppsError

RELATION_NAME = "auth-proxy"
INTERFACE_NAME = "auth_proxy"

logger = logging.getLogger(__name__)

ALLOWED_HEADERS = [
    "X-Auth-Request-User",
    "X-Auth-Request-Groups",
    "X-Auth-Request-Email",
    "X-Auth-Request-Preferred-Username",
]

url_regex = re.compile(
    r"(^http://)|(^https://)"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|"
    r"[A-Z0-9-]{2,}\.?)|"  # domain...
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

AUTH_PROXY_REQUIRER_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "https://canonical.github.io/charm-relation-interfaces/docs/json_schemas/auth_proxy/v0/requirer.json",
    "type": "object",
    "properties": {
        "protected_urls": {"type": "array", "default": None, "items": {"type": "string"}},
        "allowed_endpoints": {"type": "array", "default": [], "items": {"type": "string"}},
        "headers": {
            "type": "array",
            "default": ["X-Auth-Request-User"],
            "items": {
                "enum": ALLOWED_HEADERS,
                "type": "string",
            },
        },
        "authenticated_emails": {"type": "array", "default": [], "items": {"type": "string"}},
        "authenticated_email_domains": {
            "type": "array",
            "default": [],
            "items": {"type": "string"},
        },
        "app_name": {"type": "string", "default": None},
    },
    "required": [
        "protected_urls",
        "allowed_endpoints",
        "headers",
        "authenticated_emails",
        "authenticated_email_domains",
    ],
}


class AuthProxyConfigError(Exception):
    """Emitted when invalid auth proxy config is provided."""


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
    """Serializes data and checks whether it matches `schema`."""
    if schema:
        _validate_data(data, schema)

    ret: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            try:
                ret[k] = json.dumps(v)
            except json.JSONDecodeError as e:
                raise DataValidationError(f"Failed to encode relation json: {e}") from e
        else:
            ret[k] = str(v) if v is not None else ""
    return ret


def _validate_data(data: dict[str, Any], schema: dict[str, Any]) -> None:
    """Checks whether `data` matches `schema`.

    Will raise DataValidationError if the data is not valid, else return None.
    """
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise DataValidationError(data, schema) from e


class AuthProxyRelation(Object):
    """A class containing helper methods for auth-proxy relation."""

    _charm: CharmBase
    _relation_name: str

    def _pop_relation_data(self, relation_id: int) -> None:
        """Clear all relation data from the relation databag."""
        if not self.model.unit.is_leader():
            return

        if not self._charm.model.relations[self._relation_name]:
            return

        relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        if not relation or not relation.app:
            return

        try:
            for data in list(relation.data[self.model.app]):
                relation.data[self.model.app].pop(data, "")
        except Exception as e:
            logger.info("Failed to pop the relation data: %s", e)


@dataclass
class AuthProxyConfig:
    """Helper class containing a configuration for the charm related with OAuth2 Proxy."""

    protected_urls: list[str]
    headers: list[str] = field(default_factory=lambda: [])
    allowed_endpoints: list[str] = field(default_factory=lambda: [])
    authenticated_emails: list[str] = field(default_factory=lambda: [])
    authenticated_email_domains: list[str] = field(default_factory=lambda: [])
    app_name: str | None = None

    def validate(self) -> None:
        """Validate the auth proxy configuration."""
        # Validate protected_urls
        for url in self.protected_urls:
            if not re.match(url_regex, url):
                raise AuthProxyConfigError(f"Invalid URL {url}")

        for url in self.protected_urls:
            if url.startswith("http://"):
                logger.warning(
                    "Provided URL %s uses http scheme. Don't do this in production", url
                )

        # Validate headers
        for header in self.headers:
            if header not in ALLOWED_HEADERS:
                raise AuthProxyConfigError(
                    f"Unsupported header {header}, it must be one of {ALLOWED_HEADERS}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert object to dict."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class AuthProxyConfigChangedEvent(EventBase):
    """Event to notify the Provider charm that the auth proxy config has changed."""

    def __init__(
        self,
        handle: Handle,
        protected_urls: list[str],
        headers: list[str],
        allowed_endpoints: list[str],
        authenticated_emails: list[str],
        authenticated_email_domains: list[str],
        relation_id: int,
        relation_app_name: str,
    ) -> None:
        super().__init__(handle)
        self.protected_urls = protected_urls
        self.allowed_endpoints = allowed_endpoints
        self.headers = headers
        self.authenticated_emails = authenticated_emails
        self.authenticated_email_domains = authenticated_email_domains
        self.relation_id = relation_id
        self.relation_app_name = relation_app_name

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            "protected_urls": self.protected_urls,
            "headers": self.headers,
            "allowed_endpoints": self.allowed_endpoints,
            "authenticated_emails": self.authenticated_emails,
            "authenticated_email_domains": self.authenticated_email_domains,
            "relation_id": self.relation_id,
            "relation_app_name": self.relation_app_name,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.protected_urls = snapshot["protected_urls"]
        self.headers = snapshot["headers"]
        self.allowed_endpoints = snapshot["allowed_endpoints"]
        self.authenticated_emails = snapshot["authenticated_emails"]
        self.authenticated_email_domains = snapshot["authenticated_email_domains"]
        self.relation_id = snapshot["relation_id"]
        self.relation_app_name = snapshot["relation_app_name"]

    def to_auth_proxy_config(self) -> AuthProxyConfig:
        """Convert the event information to an AuthProxyConfig object."""
        return AuthProxyConfig(
            self.protected_urls,
            self.headers,
            self.allowed_endpoints,
            self.authenticated_emails,
            self.authenticated_email_domains,
        )


class AuthProxyConfigRemovedEvent(EventBase):
    """Event to notify the provider charm that the auth proxy config was removed."""

    def __init__(
        self,
        handle: Handle,
        relation_id: int,
    ) -> None:
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {"relation_id": self.relation_id}

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.relation_id = snapshot["relation_id"]


class AuthProxyProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `AuthProxyProvider`."""

    proxy_config_changed = EventSource(AuthProxyConfigChangedEvent)
    config_removed = EventSource(AuthProxyConfigRemovedEvent)


class AuthProxyProvider(AuthProxyRelation):
    """Provider side of the auth-proxy relation."""

    on = AuthProxyProviderEvents()  # pyright: ignore[reportAssignmentType,reportIncompatibleMethodOverride]

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_relation_changed_event)
        self.framework.observe(events.relation_broken, self._on_relation_broken_event)

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Get the auth-proxy config and emit a custom config-changed event."""
        if not self.model.unit.is_leader():
            return

        data = event.relation.data[event.app]
        if not data:
            logger.info("No requirer relation data available.")
            return

        try:
            auth_proxy_data = _load_data(data, AUTH_PROXY_REQUIRER_JSON_SCHEMA)
        except DataValidationError as e:
            logger.error(
                "Received invalid config from the requirer: %s. "
                "Config-changed will not be emitted",
                e,
            )
            return

        protected_urls = auth_proxy_data.get("protected_urls")
        allowed_endpoints = auth_proxy_data.get("allowed_endpoints")
        headers = auth_proxy_data.get("headers")
        authenticated_emails = auth_proxy_data.get("authenticated_emails")
        authenticated_email_domains = auth_proxy_data.get("authenticated_email_domains")

        relation_id = event.relation.id
        relation_app_name = event.relation.app.name

        # Notify OAuth2 Proxy to reconfigure
        self.on.proxy_config_changed.emit(
            protected_urls,
            headers,
            allowed_endpoints,
            authenticated_emails,
            authenticated_email_domains,
            relation_id,
            relation_app_name,
        )

    def _on_relation_broken_event(self, event: RelationBrokenEvent) -> None:
        """Wipe the relation databag and notify OAuth2 Proxy that the relation is broken."""
        # Workaround for https://github.com/canonical/operator/issues/888
        self._pop_relation_data(event.relation.id)

        self.on.config_removed.emit(event.relation.id)

    def get_app_names(self) -> list[str]:
        """Returns the list of all related app names."""
        if not self._charm.model.relations[self._relation_name]:
            return []

        return [
            relation.data[relation.app].get("app_name", relation.app.name)
            for relation in self._charm.model.relations[self._relation_name]
            if relation.app
        ]

    def get_decoded_relations_data(self) -> list[dict[str, Any]]:
        """Return decoded app databags for all auth-proxy relations."""
        decoded: list[dict[str, Any]] = []
        relations = self._charm.model.relations.get(self._relation_name, [])

        for relation in relations:
            if not relation.app:
                continue

            if not (raw_data := relation.data.get(relation.app)):
                continue

            try:
                decoded.append(_load_data(raw_data))
            except DataValidationError:
                continue

        return decoded

    def _normalize_relation_value(self, key: str, value: Any) -> list[str] | None:
        """Normalize a relation value into list[str], filtering empty values."""
        if value is None:
            return []

        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = cast("list[Any]", value)
        else:
            logger.error(
                "Invalid relation data for key '%s': expected list[str] or str, got %s",
                key,
                type(value).__name__,
            )
            return None

        return [v.strip() for v in values if isinstance(v, str) and v.strip()]

    def get_relations_data(self, key: str) -> list[str] | None:
        """Returns a list of key values from all auth-proxy relations or None."""
        if not self._charm.model.relations[self._relation_name]:
            return None

        relations_data: set[str] = set()

        for data in self.get_decoded_relations_data():
            if normalized := self._normalize_relation_value(key, data.get(key)):
                relations_data.update(normalized)

        return list(relations_data)


class InvalidAuthProxyConfigEvent(EventBase):
    """Event to notify the charm that the auth proxy configuration is invalid."""

    def __init__(self, handle: Handle, error: str) -> None:
        super().__init__(handle)
        self.error = error

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {
            "error": self.error,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        self.error = snapshot["error"]


class AuthProxyRelationRemovedEvent(EventBase):
    """Custom event to notify the charm that the relation was removed."""

    def snapshot(self) -> dict[str, Any]:
        """Save event."""
        return {}

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore event."""
        pass


class AuthProxyRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `AuthProxyRequirer`."""

    invalid_auth_proxy_config = EventSource(InvalidAuthProxyConfigEvent)
    auth_proxy_relation_removed = EventSource(AuthProxyRelationRemovedEvent)


class AuthProxyRequirer(AuthProxyRelation):
    """Requirer side of the auth-proxy relation."""

    on = AuthProxyRequirerEvents()  # pyright: ignore[reportAssignmentType,reportIncompatibleMethodOverride]

    def __init__(
        self,
        charm: CharmBase,
        auth_proxy_config: AuthProxyConfig | None = None,
        relation_name: str = RELATION_NAME,
    ) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._auth_proxy_config = auth_proxy_config

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created_event)
        self.framework.observe(events.relation_broken, self._on_relation_broken_event)

    def _on_relation_created_event(self, event: RelationCreatedEvent) -> None:
        """Update the relation with auth proxy config when a relation is created."""
        if not self.model.unit.is_leader():
            return

        try:
            self._update_relation_data(self._auth_proxy_config, event.relation.id)
        except AuthProxyConfigError as e:
            self.on.invalid_auth_proxy_config.emit(e.args[0])

    def _on_relation_broken_event(self, event: RelationBrokenEvent) -> None:
        """Wipe the relation databag and notify the charm when the relation is broken."""
        # Workaround for https://github.com/canonical/operator/issues/888
        self._pop_relation_data(event.relation.id)

        self.on.auth_proxy_relation_removed.emit()

    def _update_relation_data(
        self, auth_proxy_config: AuthProxyConfig | None, relation_id: int | None = None
    ) -> None:
        """Validate the auth-proxy config and update the relation databag."""
        if not self.model.unit.is_leader():
            return

        if not auth_proxy_config:
            logger.info("Auth proxy config is missing")
            return

        if type(auth_proxy_config) is not AuthProxyConfig:
            raise ValueError(f"Unexpected auth_proxy_config type: {type(auth_proxy_config)}")

        auth_proxy_config.validate()

        try:
            relation = self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        except TooManyRelatedAppsError as e:
            raise RuntimeError(
                "More than one relations are defined. Please provide a relation_id"
            ) from e

        if not relation or not relation.app:
            return

        data = _dump_data(auth_proxy_config.to_dict(), AUTH_PROXY_REQUIRER_JSON_SCHEMA)
        data["app_name"] = self._charm.app.name
        relation.data[self.model.app].update(data)

    def update_auth_proxy_config(
        self, auth_proxy_config: AuthProxyConfig, relation_id: int | None = None
    ) -> None:
        """Update the auth proxy config stored in the object."""
        self._update_relation_data(auth_proxy_config, relation_id=relation_id)
