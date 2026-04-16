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


class ClaimToHeaderData(BaseModel):
    """Maps a JWT claim to a request header."""

    model_config = ConfigDict(frozen=True)

    header: str = Field(description='Target request header name')
    claim: str = Field(description='JWT claim name to extract')


class FromHeaderData(BaseModel):
    """Specifies a header location from which to extract a JWT."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description='Header name')
    prefix: str | None = None


class JWTRuleData(BaseModel):
    """A single JWT validation rule provided by the requiring app."""

    model_config = ConfigDict(frozen=True)

    # The following fields mirror the JWTRule entry in the RequestAuthentication CRD.
    # For details check https://istio.io/latest/docs/reference/config/security/request_authentication/#JWTRule
    issuer: str = Field(description='Issuer URL for token validation')
    jwks_uri: str | None = None
    audiences: list[str] | None = None
    forward_original_token: bool | None = None
    # claim_to_headers allows
    # - mapping a single claim to multiple from_headers
    # - mapping multiple claims to the same header
    #   (in this case all available claims will be concatenated with a comma separator. missing claims will be skipped)
    claim_to_headers: list[ClaimToHeaderData] | None = None
    # from_headers allows defining multiple potential header sources. The first one with a valid token will be used.
    from_headers: list[FromHeaderData] | None = None


class RequestAuthData(BaseModel):
    """Data sent by the requirer over the istio-request-auth relation."""

    model_config = ConfigDict(frozen=True)

    jwt_rules: list[JWTRuleData] = Field(description='List of JWT validation rules')


class IstioRequestAuthProvider(Object):
    """Provider side of the istio-request-auth interface.

    Used by the ingress charm to read JWT authentication rules from all related applications.
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
        """Check if any related application has provided request auth data.

        Returns:
            True if at least one requirer has published data, False otherwise.
        """
        return bool(self.get_data())

    def get_data(self) -> dict[str, RequestAuthData]:
        """Retrieve request auth data from all related applications.

        Returns:
            A dict mapping application name to its RequestAuthData.
        """
        result: dict[str, RequestAuthData] = {}
        relations = self._charm.model.relations.get(self._relation_name, [])

        for relation in relations:
            if not relation.app:
                continue

            data_json = relation.data[relation.app].get('request_auth_data')
            if not data_json:
                continue

            try:
                auth_data = RequestAuthData.model_validate_json(data_json)
                result[relation.app.name] = auth_data
            except Exception as e:
                logger.exception('Failed to parse request auth data from %s: %s', relation.app.name, e)

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

    def publish_data(self, data: RequestAuthData) -> None:
        """Publish request auth data to the provider.

        Args:
            data: The RequestAuthData to publish.
        """
        if not self._charm.unit.is_leader():
            logger.debug('Not leader, skipping request auth data publication')
            return

        relations = self._charm.model.relations.get(self._relation_name, [])

        for relation in relations:
            relation.data[self._charm.app]['request_auth_data'] = data.model_dump_json()
