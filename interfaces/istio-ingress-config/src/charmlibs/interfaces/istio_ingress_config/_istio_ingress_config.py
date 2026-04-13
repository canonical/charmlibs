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

"""Istio ingress config interface implementation.

Migrated from istio-k8s-operator lib/charms/istio_k8s/v0/istio_ingress_config.py.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ops import Application, Relation, RelationMapping

# Default headers for external authorization.
# These defaults are based on oauth2-proxy requirements and can be used by ingress charms
# when no headers are provided by the auth provider.
DEFAULT_INCLUDE_HEADERS_IN_CHECK = ['authorization', 'cookie']
DEFAULT_HEADERS_TO_UPSTREAM_ON_ALLOW = [
    'authorization',
    'path',
    'x-auth-request-user',
    'x-auth-request-email',
    'x-auth-request-access-token',
]
DEFAULT_HEADERS_TO_DOWNSTREAM_ON_ALLOW = ['set-cookie']
DEFAULT_HEADERS_TO_DOWNSTREAM_ON_DENY = ['content-type', 'set-cookie']

DEFAULT_RELATION_NAME = 'istio-ingress-config'

FAKE_EXT_AUTHZ_SERVICE_NAME = 'fake_host'
FAKE_EXT_AUTHZ_PORT = '5432'

logger = logging.getLogger(__name__)


def _load_data(data: Mapping[str, str]) -> dict[str, str | list[str] | dict[str, str]]:
    """Parse JSON arrays/objects in databag values back to Python lists/dicts."""
    ret: dict[str, str | list[str] | dict[str, str]] = {}
    for k, v in data.items():
        ret[k] = _try_parse_json(v)
    return ret


def _try_parse_json(v: str) -> str | list[str] | dict[str, str]:
    """Attempt to parse a string as JSON, returning the original if not a list/dict."""
    try:
        parsed: object = json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return v
    if isinstance(parsed, list):
        return cast('list[str]', parsed)
    if isinstance(parsed, dict):
        return cast('dict[str, str]', parsed)
    return v


def _dump_data(data: dict[str, object]) -> dict[str, str]:
    """Serialize lists and dicts to JSON strings for databag storage."""
    ret: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            ret[k] = json.dumps(v)
        else:
            ret[k] = str(v)
    return ret


class ProviderIngressConfigData(BaseModel):
    """Data model for the provider side of the relation.

    Holds the external authorizer service name, port, and header configuration.
    """

    ext_authz_service_name: str | None = Field(
        default=None,
        description='The external authorizer service name provided by the ingress charm.',
    )
    ext_authz_port: str | None = Field(
        default=None,
        description='The port on which the external authorizer service is exposed.',
    )
    include_headers_in_check: list[str] | None = Field(
        default=None,
        description='Headers to forward to the external authorizer for checking.',
    )
    headers_to_upstream_on_allow: list[str] | None = Field(
        default=None,
        description='Headers to pass to upstream services when authorization is granted.',
    )
    headers_to_downstream_on_allow: list[str] | None = Field(
        default=None,
        description='Headers to send to the client when authorization is granted.',
    )
    headers_to_downstream_on_deny: list[str] | None = Field(
        default=None,
        description='Headers to send to the client when authorization is denied.',
    )

    @field_validator('ext_authz_port')
    @classmethod
    def validate_ext_authz_port(cls, port: str | None) -> str | None:
        """Ensure port is convertible to int."""
        if port is None:
            return port
        try:
            int(port)
        except ValueError:
            msg = f'ext_authz_port must be convertible to an integer, got {port!r}'
            raise ValueError(msg) from None
        return port


class RequirerIngressConfigData(BaseModel):
    """Data model for the requirer side of the relation.

    Holds the generated external authorizer provider name.
    """

    ext_authz_provider_name: str | None = Field(
        default=None,
        description='The generated external authorizer provider name.',
    )


class IngressConfigProvider:
    """Provider side wrapper for the istio-ingress-config relation.

    The provider (ingress charm) publishes its external authorizer service name and port and
    can fetch the generated external authorizer provider name from the requirer's databag.
    """

    def __init__(
        self,
        relation_mapping: RelationMapping,
        app: Application,
        relation_name: str = DEFAULT_RELATION_NAME,
    ) -> None:
        """Initialize the IngressConfigProvider.

        Args:
            relation_mapping: The charm's RelationMapping (typically self.model.relations).
            app: This application (the ingress charm).
            relation_name: The name of the relation.
        """
        self._charm_relation_mapping = relation_mapping
        self._app = app
        self._relation_name = relation_name

    @property
    def relations(self) -> list[Relation]:
        """Return the relation instances for the monitored relation."""
        return self._charm_relation_mapping.get(self._relation_name, [])

    def publish(
        self,
        ext_authz_service_name: str | None = None,
        ext_authz_port: str | None = None,
        include_headers_in_check: list[str] | None = None,
        headers_to_upstream_on_allow: list[str] | None = None,
        headers_to_downstream_on_allow: list[str] | None = None,
        headers_to_downstream_on_deny: list[str] | None = None,
    ) -> None:
        """Publish external authorizer configuration data to all related applications.

        Args:
            ext_authz_service_name: The external authorizer service name.
            ext_authz_port: The port number for the external authorizer service.
            include_headers_in_check: Headers to forward to the external authorizer for checking.
            headers_to_upstream_on_allow: Headers to pass to upstream on successful auth.
            headers_to_downstream_on_allow: Headers to send to client on successful auth.
            headers_to_downstream_on_deny: Headers to send to client on denied auth.
        """
        data = ProviderIngressConfigData(
            ext_authz_service_name=ext_authz_service_name,
            ext_authz_port=ext_authz_port,
            include_headers_in_check=include_headers_in_check,
            headers_to_upstream_on_allow=headers_to_upstream_on_allow,
            headers_to_downstream_on_allow=headers_to_downstream_on_allow,
            headers_to_downstream_on_deny=headers_to_downstream_on_deny,
        ).model_dump(mode='json', by_alias=True, exclude_defaults=True, round_trip=True)
        serialized = _dump_data(data)

        for relation in self.relations:
            databag = relation.data[self._app]
            databag.update(serialized)
            logger.debug('Published provider data: %s to relation: %s', serialized, relation)

    def clear(self) -> None:
        """Clear the local application databag.

        Workaround for https://github.com/juju/juju/issues/19474:
        we cannot clear a databag in cross-model relations, so we publish a fake config instead.
        """
        self.publish(
            ext_authz_service_name=FAKE_EXT_AUTHZ_SERVICE_NAME,
            ext_authz_port=FAKE_EXT_AUTHZ_PORT,
        )

    def get_ext_authz_provider_name(self) -> str | None:
        """Fetch the external authorizer provider name generated by the requirer.

        Returns:
            The generated external authorizer provider name if available, else None.
        """
        if not self.relations:
            return None

        relation = self.relations[0]
        raw_data = getattr(relation, 'data', {}).get(relation.app, {})
        if not raw_data:
            return None
        try:
            return RequirerIngressConfigData.model_validate(raw_data).ext_authz_provider_name
        except Exception:
            logger.debug('Failed to validate requirer data', exc_info=True)
            return None

    def is_ready(self) -> bool:
        """Check if the generated external authorizer provider name is present.

        Returns:
            True if the external authorizer provider name has been published by the requirer.
        """
        return self.get_ext_authz_provider_name() is not None


class IngressConfigRequirer:
    """Requirer side wrapper for the istio-ingress-config relation.

    The requirer generates and publishes a unique external authorizer provider name
    for a connected ingress charm. It can also check that the provider has published
    its required external authorizer service configuration.
    """

    def __init__(
        self,
        relation_mapping: RelationMapping,
        app: Application,
        relation_name: str = DEFAULT_RELATION_NAME,
    ) -> None:
        """Initialize the IngressConfigRequirer.

        Args:
            relation_mapping: The charm's RelationMapping (typically self.model.relations).
            app: This application.
            relation_name: The name of the relation.
        """
        self._charm_relation_mapping = relation_mapping
        self._app = app
        self._relation_name = relation_name

    @property
    def relations(self) -> list[Relation]:
        """Return the relation instances for the monitored relation."""
        return self._charm_relation_mapping.get(self._relation_name, [])

    def publish_ext_authz_provider_name(self, relation: Relation, unique_name: str) -> None:
        """Publish a unique external authorizer provider name for a connected ingress charm.

        Args:
            relation: A specific relation instance.
            unique_name: The unique external authorizer provider name to publish.
        """
        data = RequirerIngressConfigData(
            ext_authz_provider_name=unique_name,
        ).model_dump(mode='json', by_alias=True, exclude_defaults=True, round_trip=True)
        relation.data[self._app].update(data)
        logger.debug('Published requirer data: %s', data)

    def get_provider_ext_authz_info(self, relation: Relation) -> ProviderIngressConfigData | None:
        """Retrieve the provider's external authorizer configuration for the given relation.

        Args:
            relation: A specific relation instance.

        Returns:
            An instance of ProviderIngressConfigData if available and valid, else None.
        """
        raw_data = getattr(relation, 'data', {}).get(relation.app, {})
        if not raw_data:
            return None
        try:
            parsed_data = _load_data(raw_data)
            return ProviderIngressConfigData.model_validate(parsed_data)
        except Exception:
            logger.debug('Failed to validate provider data', exc_info=True)
            return None

    def is_fake_authz_config(self, relation: Relation) -> bool:
        """Check if the provider has published a fake external authorization configuration.

        Workaround for https://github.com/juju/juju/issues/19474:
        we cannot clear a databag in cross-model relations, so we publish a fake config instead.

        Args:
            relation: A specific relation instance.

        Returns:
            True if the provider relation contains fake authz configuration, else False.
        """
        provider_info = self.get_provider_ext_authz_info(relation)
        if provider_info is not None:
            return (
                provider_info.ext_authz_service_name == FAKE_EXT_AUTHZ_SERVICE_NAME
                and provider_info.ext_authz_port == FAKE_EXT_AUTHZ_PORT
            )
        return False

    def is_ready(self, relation: Relation) -> bool:
        """Check if the provider has published its external authorizer service configuration.

        Args:
            relation: A specific relation instance.

        Returns:
            True if both ext_authz_service_name and ext_authz_port are present.
        """
        provider_info = self.get_provider_ext_authz_info(relation)
        if provider_info is None:
            return False
        return (
            provider_info.ext_authz_service_name is not None
            and provider_info.ext_authz_port is not None
        )

    def get_ext_authz_provider_name(self, relation: Relation) -> str | None:
        """Retrieve the generated external authorizer provider name for the given relation.

        Args:
            relation: A specific relation instance.

        Returns:
            The external authorizer provider name if available, else None.
        """
        raw_data = getattr(relation, 'data', {}).get(self._app, {})
        if not raw_data:
            return None
        try:
            requirer_data = RequirerIngressConfigData.model_validate(raw_data)
            return requirer_data.ext_authz_provider_name
        except Exception:
            logger.debug('Failed to retrieve external authorizer provider name', exc_info=True)
            return None
