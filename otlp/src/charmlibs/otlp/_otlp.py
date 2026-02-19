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

"""Internal implementation of the OTLP Provider and Requirer library.

This document explains how to integrate with charms that can send/receive OTLP data.
This document is the authoritative reference on the structure of relation data that is
shared between charms that intend to provide or consume OTLP telemetry.
For user-facing documentation, see the package-level docstring in __init__.py.
"""

import json
import logging
import socket
from collections.abc import Sequence
from typing import ClassVar, Literal

from cosl.juju_topology import JujuTopology
from ops import CharmBase, Relation
from ops.framework import Object
from pydantic import BaseModel, ConfigDict, ValidationError

DEFAULT_CONSUMER_RELATION_NAME = 'send-otlp'
DEFAULT_PROVIDER_RELATION_NAME = 'receive-otlp'
RELATION_INTERFACE_NAME = 'otlp'

logger = logging.getLogger(__name__)


class OtlpEndpoint(BaseModel):
    """A pydantic model for a single OTLP endpoint."""

    model_config = ConfigDict(extra='forbid')

    protocol: Literal['http', 'grpc']
    endpoint: str
    telemetries: Sequence[Literal['logs', 'metrics', 'traces']]


class OtlpProviderAppData(BaseModel):
    """A pydantic model for the OTLP provider's unit databag."""

    KEY: ClassVar[str] = 'otlp'

    model_config = ConfigDict(extra='forbid')

    endpoints: list[OtlpEndpoint]


class OtlpConsumer(Object):
    """A class for consuming OTLP endpoints."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_CONSUMER_RELATION_NAME,
        protocols: Sequence[Literal['http', 'grpc']] | None = None,
        telemetries: Sequence[Literal['logs', 'metrics', 'traces']] | None = None,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._protocols: list[Literal['http', 'grpc']] = (
            list(protocols) if protocols is not None else []
        )
        self._telemetries: list[Literal['logs', 'metrics', 'traces']] = (
            list(telemetries) if telemetries is not None else []
        )
        self.topology = JujuTopology.from_charm(charm)

    def _get_provider_databag(self, otlp_databag: str) -> OtlpProviderAppData | None:
        """Load the OtlpProviderAppData from the given databag string.

        For each endpoint in the databag, if it contains unsupported telemetry types, those
        telemetries are filtered out before validation. If an endpoint contains an unsupported
        protocol, or has no supported telemetries, it is skipped entirely.
        """
        try:
            data = json.loads(otlp_databag)
            endpoints_data = data.get('endpoints', [])
        except json.JSONDecodeError as e:
            logger.error('Failed to parse OTLP databag: %s', e)

            return None

        valid_endpoints: list[OtlpEndpoint] = []
        supported_telemetries: set[Literal['logs', 'metrics', 'traces']] = set(self._telemetries)
        for endpoint_data in endpoints_data:
            if filtered_telemetries := [
                t for t in endpoint_data.get('telemetries', []) if t in supported_telemetries
            ]:
                endpoint_data['telemetries'] = filtered_telemetries
            else:
                # If there are no supported telemetries for this endpoint, skip it entirely
                continue
            try:
                endpoint = OtlpEndpoint.model_validate(endpoint_data)
            except ValidationError:
                continue
            valid_endpoints.append(endpoint)
        try:
            return OtlpProviderAppData(endpoints=valid_endpoints)
        except ValidationError as e:
            logger.error('OTLP databag failed validation %s', e)
            return None

    def get_remote_otlp_endpoints(self) -> dict[int, OtlpEndpoint]:
        """Return a mapping of relation ID to OTLP endpoint.

        For each remote unit's list of OtlpEndpoints:
            - If a telemetry type is not supported, then the endpoint is accepted, but the
              telemetry is ignored.
            - If the endpoint contains an unsupported protocol it is ignored.
            - The first available (and supported) endpoint is returned.

        Returns:
            Dict mapping relation ID -> OtlpEndpoint
        """
        endpoints: dict[int, OtlpEndpoint] = {}
        for rel in self.model.relations[self._relation_name]:
            if not (otlp := rel.data[rel.app].get(OtlpProviderAppData.KEY)):
                continue
            if not (app_databag := self._get_provider_databag(otlp)):
                continue

            # Choose the first valid endpoint in list
            if endpoint_choice := next(
                (e for e in app_databag.endpoints if e.protocol in self._protocols), None
            ):
                endpoints[rel.id] = endpoint_choice

        return endpoints


class OtlpProvider(Object):
    """A class for publishing all supported OTLP endpoints.

    Args:
        charm: The charm instance.
        protocol_ports: A dictionary mapping ProtocolType to port number.
        relation_name: The name of the relation to use.
        path: An optional path to append to the endpoint URLs.
        supported_telemetries: A list of supported telemetry types.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_PROVIDER_RELATION_NAME,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._endpoints: list[OtlpEndpoint] = []

    @property
    def internal_url(self) -> str:
        """Return the internal URL for the OTLP provider."""
        return f'http://{socket.getfqdn()}'

    def add_endpoint(
        self,
        protocol: Literal['http', 'grpc'],
        endpoint: str,
        telemetries: Sequence[Literal['logs', 'metrics', 'traces']],
    ):
        """Add an OtlpEndpoint to the list.

        Call this method after endpoint-changing events e.g. TLS and ingress.
        """
        self._endpoints.append(
            OtlpEndpoint(protocol=protocol, endpoint=endpoint, telemetries=telemetries)
        )

    def publish(self, relation: Relation | None = None) -> None:
        """Triggers programmatically the update of the relation data.

        Args:
            url: An optional URL to use instead of the internal URL.
            relation: An optional instance of `class:ops.model.Relation` to update.
                If not provided, all instances of the `otlp`
                relation are updated.
        """
        if not self._charm.unit.is_leader():
            # Only the leader unit can write to app data.
            return

        relations = [relation] if relation else self.model.relations[self._relation_name]
        for relation in relations:
            data = OtlpProviderAppData(endpoints=self._endpoints).model_dump(exclude_none=True)
            otlp = {OtlpProviderAppData.KEY: data}
            relation.data[self._charm.app].update({k: json.dumps(v) for k, v in otlp.items()})
