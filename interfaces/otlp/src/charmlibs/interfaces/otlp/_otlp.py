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

This document is the authoritative reference on the structure of relation data that is
shared between charms that intend to provide or consume OTLP telemetry.
For user-facing documentation, see the package-level docstring in __init__.py.
"""

import json
import logging
from collections import OrderedDict
from collections.abc import Sequence
from typing import Any, Final, Literal

from cosl.juju_topology import JujuTopology
from cosl.utils import LZMABase64
from ops import CharmBase
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
)

from ._rules import (
    RuleStore,
    _RulesModel,
    inject_extra_labels_to_alert_rules,
    inject_generic_rules,
)

DEFAULT_REQUIRER_RELATION_NAME = 'send-otlp'
DEFAULT_PROVIDER_RELATION_NAME = 'receive-otlp'
DEFAULT_LOKI_RULES_RELATIVE_PATH = './src/loki_alert_rules'
DEFAULT_PROM_RULES_RELATIVE_PATH = './src/prometheus_alert_rules'


logger = logging.getLogger(__name__)


class OtlpEndpoint(BaseModel):
    """A pydantic model for a single OTLP endpoint."""

    protocol: str = Field(
        description='Transport protocol used to send telemetry data to this endpoint.'
    )
    endpoint: str = Field(description="URL of the OTLP endpoint (e.g. 'http://collector:4318').")
    telemetries: Sequence[str] = Field(
        description='Telemetry signal types accepted by this endpoint.'
    )
    insecure: bool = Field(
        description='Whether this endpoint requires an insecure connection (e.g. no TLS).',
        default=False,
    )


class _OtlpEndpoint(OtlpEndpoint):
    """A pydantic model for a single OTLP endpoint."""


class _OtlpProviderAppData(BaseModel):
    """A pydantic model for the OTLP provider's app databag."""

    endpoints: list[_OtlpEndpoint] = Field(
        description='List of OTLP endpoints exposed by the provider.'
    )


class _OtlpRequirerAppData(BaseModel):
    """A pydantic model for the OTLP requirer's app databag.

    The rules are compressed when saved to databag to avoid hitting databag
    size limits for large deployments. An admin can decode the rules using the
    following command:
    ```bash
    <rules-from-show-unit> | base64 -d | xz -d | jq
    ```
    """

    rules: _RulesModel = Field(
        description='Rules to be forwarded to the provider.'
        ' Stored as an LZMA-compressed, base64-encoded JSON string to reduce payload size.'
    )
    metadata: OrderedDict[str, str] = Field(
        description='Juju topology of the requirer charm (e.g. model, app, unit),'
        ' used to label rule expressions and alert routing.'
    )

    @field_validator('rules', mode='before')
    @classmethod
    def _deserialize_rules(cls, rules: str | dict[str, Any] | _RulesModel) -> Any:
        """Decompress LZMA-compressed rules from the relation databag."""
        if isinstance(rules, str):
            return json.loads(LZMABase64.decompress(rules))
        return rules

    @field_serializer('rules')
    def _serialize_rules(self, rules: _RulesModel) -> str:
        """LZMA-compress rules to reduce content size for larger deployments."""
        return LZMABase64.compress(rules.model_dump_json())


class OtlpRequirer:
    """A class for consuming OTLP endpoints.

    Args:
        charm: The charm instance.
        relation_name: The name of the relation to use.
        protocols: The protocols to filter for in the provider's OTLP
            endpoints.
        telemetries: The telemetries to filter for in the provider's OTLP
            endpoints.
        aggregator_peer_relation_name: Name of the peers relation of this
            charm. This should only be set IFF the charm is an aggregator AND
            it has a peer relation with this name. When provided, generic
            aggregator rules are used instead of application-level rules.
        rules: Rules of different types e.g., logql or promql, that the
            requirer will publish for the provider.
        extra_alert_labels: Dict of extra labels to inject alert rules with.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_REQUIRER_RELATION_NAME,
        protocols: Sequence[Literal['http', 'grpc']] | None = None,
        telemetries: Sequence[Literal['logs', 'metrics', 'traces']] | None = None,
        *,
        aggregator_peer_relation_name: str | None = None,
        rules: RuleStore | None = None,
        extra_alert_labels: dict | None = None,
    ):
        self._charm = charm
        self._topology = JujuTopology.from_charm(charm)
        self._relation_name = relation_name
        self._protocols: list[Literal['http', 'grpc']] = (
            list(protocols) if protocols is not None else []
        )
        self._telemetries: list[Literal['logs', 'metrics', 'traces']] = (
            list(telemetries) if telemetries is not None else []
        )
        self._aggregator_peer_relation_name = aggregator_peer_relation_name
        self._rules = rules if rules is not None else RuleStore(self._topology)
        self._extra_alert_labels = extra_alert_labels or {}

    def _filter_endpoints(self, endpoints: list[_OtlpEndpoint]) -> list[_OtlpEndpoint]:
        """Filter out unsupported OtlpEndpoints.

        For each endpoint:
            - If a telemetry type is not supported, then the endpoint is
              accepted, but the telemetry is ignored.
            - If there are no supported telemetries for this endpoint, the
              endpoint is ignored.
            - If the endpoint contains an unsupported protocol it is ignored.
        """
        valid_endpoints: list[_OtlpEndpoint] = []
        supported_telemetries = set(self._telemetries)
        for endpoint in endpoints:
            if endpoint.protocol not in self._protocols:
                # If the endpoint contains an unsupported protocol, skip it entirely
                continue
            if filtered_telemetries := [
                t for t in endpoint.telemetries if t in supported_telemetries
            ]:
                endpoint.telemetries = filtered_telemetries
            else:
                # If there are no supported telemetries for this endpoint, skip it entirely
                continue

            valid_endpoints.append(endpoint)

        return valid_endpoints

    def _favor_modern_endpoints(self, endpoints: list[_OtlpEndpoint]) -> _OtlpEndpoint:
        """Return the preferred endpoint using protocol priority.

        Modern protocols receive higher priority.
        Protocol ranking is `grpc` > `http`; unknown protocols rank lowest.
        """
        modern_score: Final = {'grpc': 2, 'http': 1}
        return max(endpoints, key=lambda e: modern_score.get(e.protocol, 0))

    def _handle_alert_rules(self) -> RuleStore:
        """Maintain the rule store with common alert rule operations."""
        inject_generic_rules(
            self._charm,
            self._rules,
            self._topology,
            self._aggregator_peer_relation_name,
        )
        inject_extra_labels_to_alert_rules(self._rules, self._extra_alert_labels)

    def publish(self):
        """Triggers programmatically the update of the relation data.

        These rule sources are included when publishing:
            - Any rules provided at the instantiation of this class.
            - Generic (not specific to any charm) PromQL rules.
        """
        if not self._charm.unit.is_leader():
            # Only the leader unit can write to app data.
            return

        self._handle_alert_rules()

        # Publish to databag
        databag = _OtlpRequirerAppData.model_validate({
            'rules': {
                'logql': self._rules.logql.as_dict(),
                'promql': self._rules.promql.as_dict(),
            },
            'metadata': self._topology.as_dict(),
        })
        for relation in self._charm.model.relations[self._relation_name]:
            relation.save(databag, self._charm.app)

    @property
    def endpoints(self) -> dict[int, OtlpEndpoint]:
        """Return a mapping of relation ID to OTLP endpoint.

        For each remote's list of OtlpEndpoints, the requirer filters out
        unsupported endpoints and telemetries. If multiple compatible
        endpoints remain, the requirer prefers newer protocols (`grpc` over
        `http`). Unknown protocols are treated as the lowest priority. This
        allows providers to expose multiple endpoints with different protocol
        and telemetry combinations while the requirer selects the best match.
        """
        endpoint_map: dict[int, OtlpEndpoint] = {}
        for relation in self._charm.model.relations[self._relation_name]:
            if not relation.data[relation.app]:
                # The databags haven't initialized yet, continue
                continue

            try:
                provider = relation.load(_OtlpProviderAppData, relation.app)
            except ValidationError as e:
                logger.error('OTLP databag failed validation: %s', e)
                continue
            if endpoints := self._filter_endpoints(provider.endpoints):
                endpoint_map[relation.id] = self._favor_modern_endpoints(endpoints)

        return endpoint_map


class OtlpProvider:
    """A class for publishing all supported OTLP endpoints.

    Args:
        charm: The charm instance.
        relation_name: The name of the relation to use.
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_PROVIDER_RELATION_NAME,
    ):
        self._charm = charm
        self._relation_name = relation_name
        self._endpoints: list[_OtlpEndpoint] = []
        self._topology = JujuTopology.from_charm(charm)

    def add_endpoint(
        self,
        protocol: Literal['http', 'grpc'],
        endpoint: str,
        telemetries: Sequence[Literal['logs', 'metrics', 'traces']],
        insecure: bool = False,
    ) -> 'OtlpProvider':
        """Add an OtlpEndpoint to the list of endpoints to publish."""
        self._endpoints.append(
            _OtlpEndpoint(
                protocol=protocol,
                endpoint=endpoint,
                telemetries=telemetries,
                insecure=insecure,
            )
        )
        return self

    def publish(self) -> None:
        """Triggers programmatically the update of the relation data."""
        if not self._charm.unit.is_leader():
            # Only the leader unit can write to app data.
            return

        databag = _OtlpProviderAppData.model_validate({'endpoints': self._endpoints})
        for relation in self._charm.model.relations[self._relation_name]:
            relation.save(databag, self._charm.app)

    @property
    def rules(self) -> dict[int, RuleStore]:
        """Fetch rules for all relations of the desired query and rule types.

        This method returns all rules of varying query and rule types, provided
        by related OTLP requirer charms. This method ensures rules:

            - have labels from the charm's Juju topology.
            - have expression labels from the charm's Juju topology.
            - are validated using CosTool.

        Returns:
            a mapping of relation ID to a RuleStore object.
        """
        rules_map: dict[int, RuleStore] = {}
        # Instantiate Rules with topology to ensure that rules always have an identifier
        for relation in self._charm.model.relations[self._relation_name]:
            if not relation.data[relation.app]:
                # The databags haven't initialized yet, continue
                continue

            try:
                requirer = relation.load(_OtlpRequirerAppData, relation.app)
            except ValidationError as e:
                logger.error('OTLP databag failed validation: %s', e)
                continue

            # Create a RuleStore for this relation's rules, and inject topology labels
            rules = RuleStore(self._topology)
            logql_result = rules.logql.inject_and_validate_rules(
                requirer.rules.logql, requirer.metadata
            )
            promql_result = rules.promql.inject_and_validate_rules(
                requirer.rules.promql, requirer.metadata
            )
            if logql_result.rules and not logql_result.errmsg:
                rules.logql.add(logql_result.rules)
            if promql_result.rules and not promql_result.errmsg:
                rules.promql.add(promql_result.rules)
            for errmsg in [logql_result.errmsg, promql_result.errmsg]:
                if errmsg and self._charm.unit.is_leader():
                    relation.data[self._charm.app]['event'] = json.dumps({'errors': errmsg})

            rules_map[relation.id] = rules

        return rules_map
