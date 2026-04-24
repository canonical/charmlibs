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

"""Istio request authentication interface implementation.

Migrated from charmed-service-mesh-helpers interfaces/request_auth.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ops.framework import Object
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from ops import CharmBase

logger = logging.getLogger(__name__)


class ClaimToHeader(BaseModel):
    """Maps a JWT claim to a request header."""

    model_config = ConfigDict(frozen=True)

    header: str = Field(description='Target request header name')
    claim: str = Field(description='JWT claim name to extract')


class FromHeader(BaseModel):
    """Specifies a header location from which to extract a JWT."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description='Header name')
    prefix: str | None = None


class JWTRule(BaseModel):
    """A single JWT validation rule provided by the requiring app."""

    model_config = ConfigDict(frozen=True)

    # The following fields mirror the JWTRule entry in the RequestAuthentication CRD.
    # For details check https://istio.io/latest/docs/reference/config/security/request_authentication/#JWTRule
    issuer: str = Field(description='Issuer URL for token validation')
    jwks_uri: str | None = None
    audiences: list[str] | None = None
    forward_original_token: bool | None = None
    # claim_to_headers allows mapping a single claim to multiple headers or
    # multiple claims to the same header (concatenated with comma; missing
    # claims are skipped).
    claim_to_headers: list[ClaimToHeader] | None = None
    # from_headers allows defining multiple potential header sources.
    # The first one with a valid token will be used.
    from_headers: list[FromHeader] | None = None


class _RequestAuthData(BaseModel):
    """Top-level databag model for the istio-request-auth relation.

    Each field maps directly to a top-level key in the Juju application databag.
    Use ``ops.Relation.load`` / ``ops.Relation.save`` to (de)serialise.

    ``jwt_rules`` defaults to ``None``.  When it is missing, ``None``, or an
    empty list the provider side treats the relation as not-ready and skips
    the application.
    """

    model_config = ConfigDict(frozen=True)

    jwt_rules: list[JWTRule] | None = Field(
        default=None,
        description='List of JWT validation rules. Missing or empty means not ready.',
    )


class IstioRequestAuthProvider(Object):
    """Provider side of the istio-request-auth interface.

    Used by the ingress charm to read JWT authentication rules from all related
    applications.

    Applications that are connected but have not provided valid (non-empty)
    ``jwt_rules`` are excluded from :meth:`get_data` but included in
    :meth:`get_connected_apps`.  Consumers can compare the two sets to
    identify applications that have not yet provided data::

        valid = provider.get_data()
        connected = provider.get_connected_apps()
        apps_without_data = connected - set(valid.keys())
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = 'istio-request-auth',
    ):
        """Initialize the IstioRequestAuthProvider.

        Args:
            charm: The charm that owns this provider.
            relation_name: Name of the relation (default: "istio-request-auth").
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    @property
    def is_ready(self) -> bool:
        """Check if any related application has provided valid request auth data.

        Returns:
            True if at least one requirer has published non-empty jwt_rules.
        """
        return bool(self.get_data())

    def get_connected_apps(self) -> set[str]:
        """Return the names of all applications connected over the relation.

        This includes apps that have not yet provided valid data.
        """
        apps: set[str] = set()
        for relation in self._charm.model.relations.get(self._relation_name, []):
            if relation.app:
                apps.add(relation.app.name)
        return apps

    def get_data(self) -> dict[str, list[JWTRule]]:
        """Retrieve valid JWT rules from all related applications.

        Uses ``ops.Relation.load`` to deserialise each application's databag
        into :class:`RequestAuthData`.  Only applications whose databag
        contains a non-empty ``jwt_rules`` list are included.

        Returns:
            A dict mapping application name to its list of ``JWTRule`` objects.
        """
        result: dict[str, list[JWTRule]] = {}
        relations = self._charm.model.relations.get(self._relation_name, [])

        for relation in relations:
            if not relation.app:
                continue

            app_name = relation.app.name

            try:
                data = relation.load(_RequestAuthData, relation.app)
            except Exception as e:
                logger.exception(
                    'Failed to parse databag from application %s: %s',
                    app_name,
                    e,
                )
                continue

            if not data.jwt_rules:
                logger.warning(
                    'Application %s has not provided jwt_rules',
                    app_name,
                )
                continue

            result[app_name] = data.jwt_rules

        return result


class IstioRequestAuthRequirer(Object):
    """Requirer side of the istio-request-auth interface.

    Used by downstream applications to publish their JWT authentication rules
    to the ingress charm.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = 'istio-request-auth',
    ):
        """Initialize the IstioRequestAuthRequirer.

        Args:
            charm: The charm that owns this requirer.
            relation_name: Name of the relation (default: "istio-request-auth").
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    def publish_data(self, jwt_rules: list[JWTRule]) -> None:
        """Publish JWT rules to the provider.

        Uses ``ops.Relation.save`` to write a :class:`RequestAuthData` instance
        to the application databag so ``jwt_rules`` appears as a top-level key.

        Args:
            jwt_rules: The JWT validation rules to publish.
        """
        if not self._charm.unit.is_leader():
            logger.debug('Not leader, skipping request auth data publication')
            return

        data = _RequestAuthData(jwt_rules=jwt_rules)

        for relation in self._charm.model.relations.get(self._relation_name, []):
            relation.save(data, self._charm.app)
