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

import copy
import json
import logging
from collections import OrderedDict
from collections.abc import Sequence
from lzma import LZMAError
from pathlib import Path
from typing import Any, Literal

from cosl.juju_topology import JujuTopology
from cosl.rules import AlertRules, InjectResult, generic_alert_groups
from cosl.utils import LZMABase64
from ops import CharmBase
from ops.framework import Object
from pydantic import BaseModel, ConfigDict, ValidationError

DEFAULT_CONSUMER_RELATION_NAME = 'send-otlp'
DEFAULT_PROVIDER_RELATION_NAME = 'receive-otlp'
DEFAULT_LOKI_RULES_RELATIVE_PATH = './src/loki_alert_rules'
DEFAULT_PROM_RULES_RELATIVE_PATH = './src/prometheus_alert_rules'


logger = logging.getLogger(__name__)


class RulesModel(BaseModel):
    """A pydantic model for all rule formats."""

    model_config = ConfigDict(extra='forbid')

    logql: dict[str, Any]
    promql: dict[str, Any]


class OtlpEndpoint(BaseModel):
    """A pydantic model for a single OTLP endpoint."""

    model_config = ConfigDict(extra='forbid')

    protocol: Literal['http', 'grpc']
    endpoint: str
    telemetries: Sequence[Literal['logs', 'metrics', 'traces']]


class OtlpProviderAppData(BaseModel):
    """A pydantic model for the OTLP provider's unit databag."""

    model_config = ConfigDict(extra='forbid')

    endpoints: list[OtlpEndpoint]


class OtlpConsumerAppData(BaseModel):
    """A pydantic model for the OTLP consumer's unit databag.

    The rules are compressed when saved to databag to avoid hitting databag
    size limits for large deployments. An admin can decode the rules using the
    following command:
    ```bash
    <rules-from-show-unit> | base64 -d | xz -d | jq
    ```
    """

    model_config = ConfigDict(extra='forbid')

    rules: RulesModel | str
    metadata: OrderedDict[str, str]

    @staticmethod
    def decode_value(json_str: str) -> Any:
        """Decode relation data values using BaseModel validation."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            try:
                decompressed = LZMABase64.decompress(json_str)
                return RulesModel.model_validate(json.loads(decompressed))
            except (json.JSONDecodeError, ValidationError, LZMAError):
                return ''

    @staticmethod
    def encode_value(obj: Any) -> str:
        """Encode relation data values using BaseModel serialization."""
        try:
            RulesModel.model_validate(obj)
            return LZMABase64.compress(json.dumps(obj, sort_keys=True))
        except ValidationError:
            return json.dumps(obj, sort_keys=True)


class OtlpConsumer(Object):
    """A class for consuming OTLP endpoints.

    Args:
        charm: The charm instance.
        relation_name: The name of the relation to use.
        protocols: The protocols to filter for in the provider's OTLP
            endpoints.
        telemetries: The telemetries to filter for in the provider's OTLP
            endpoints.
        loki_rules_path: The path to Loki alerting and recording rules provided
            by this charm.
        prometheus_rules_path: The path to Prometheus alerting and recording
            rules provided by this charm.
    """

    _rules_cls = AlertRules

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_CONSUMER_RELATION_NAME,
        protocols: Sequence[Literal['http', 'grpc']] | None = None,
        telemetries: Sequence[Literal['logs', 'metrics', 'traces']] | None = None,
        *,
        loki_rules_path: str | Path = DEFAULT_LOKI_RULES_RELATIVE_PATH,
        prometheus_rules_path: str | Path = DEFAULT_PROM_RULES_RELATIVE_PATH,
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
        self._topology = JujuTopology.from_charm(charm)
        # Avoid calling AlertRules.validate_rules_path here to prevent static
        # attribute-access typing complaints from analyzers; keep the provided
        # paths as-is (they are validated at runtime by callers that need it).
        self._loki_rules_path: str | Path = loki_rules_path
        self._prom_rules_path: str | Path = prometheus_rules_path

    def _filter_endpoints(self, endpoints: list[dict[str, str | list[str]]]) -> list[OtlpEndpoint]:
        """Filter out unsupported OtlpEndpoints.

        For each endpoint:
            - If a telemetry type is not supported, then the endpoint is
              accepted, but the telemetry is ignored.
            - If there are no supported telemetries for this endpoint, the
              endpoint is ignored.
            - If the endpoint contains an unsupported protocol it is ignored.
        """
        valid_endpoints: list[OtlpEndpoint] = []
        supported_telemetries = set(self._telemetries)
        for endpoint in endpoints:
            if filtered_telemetries := [
                t for t in endpoint.get('telemetries', []) if t in supported_telemetries
            ]:
                endpoint['telemetries'] = filtered_telemetries
            else:
                # If there are no supported telemetries for this endpoint, skip it entirely
                continue
            try:
                endpoint = OtlpEndpoint.model_validate(endpoint)
            except ValidationError:
                continue
            valid_endpoints.append(endpoint)

        return valid_endpoints

    def publish(self):
        """Triggers programmatically the update of the relation data.

        The rule files exist in separate directories, distinguished by format
        (logql|promql), each including alerting and recording rule types. The
        charm uses these paths as aggregation points for rules, acting as their
        source of truth. For each type of rule, the charm may aggregate rules
        from:
            - rules bundled in the charm's source code
            - any rules provided by related charms

        Generic, injected rules (not specific to any charm) are always
        published. Besides these generic rules, the inclusion of bundled rules
        and rules from related charms is the responsibility of the charm using
        the library. Including bundled rules and rules from related charms is
        achieved by copying these rules to the respective paths within the
        charm's filesystem and providing those paths to the OtlpConsumer
        constructor.
        """
        if not self._charm.unit.is_leader():
            # Only the leader unit can write to app data.
            return

        # Define the rule types
        loki_rules = self._rules_cls(query_type='logql', topology=self._topology)
        prom_rules = self._rules_cls(query_type='promql', topology=self._topology)

        # Add rules
        prom_rules.add(
            copy.deepcopy(generic_alert_groups.aggregator_rules),
            group_name_prefix=self._topology.identifier,
        )
        loki_rules.add_path(self._loki_rules_path, recursive=True)
        prom_rules.add_path(self._prom_rules_path, recursive=True)

        # Publish to databag
        databag = OtlpConsumerAppData.model_validate({
            'rules': {'logql': loki_rules.as_dict(), 'promql': prom_rules.as_dict()},
            'metadata': self._topology.as_dict(),
        })
        for relation in self.model.relations[self._relation_name]:
            relation.save(databag, self._charm.app, encoder=OtlpConsumerAppData.encode_value)

    @property
    def endpoints(self) -> dict[int, OtlpEndpoint]:
        """Return a mapping of relation ID to OTLP endpoint.

        For each remote's list of OtlpEndpoints, the consumer filters out
        unsupported endpoints and telemetries. If there are multiple supported
        endpoints, the consumer chooses the first available endpoint in the
        list. This allows providers to specify multiple endpoints with
        different protocols and/or telemetry types and the consumer can choose
        one based on its own capabilities. For example, a provider may specify
        both an HTTP and gRPC endpoint, and a consumer that only supports HTTP
        will choose the HTTP endpoint.
        """
        endpoint_map: dict[int, OtlpEndpoint] = {}
        for relation in self.model.relations[self._relation_name]:
            endpoints = json.loads(relation.data[relation.app].get('endpoints', '[]'))
            if not (endpoints := self._filter_endpoints(endpoints)):
                continue

            try:
                # Ensure that the databag is valid
                app_databag = OtlpProviderAppData(endpoints=endpoints)
            except ValidationError as e:
                logger.error('OTLP databag failed validation: %s', e)
                continue

            # Choose the first valid endpoint in list
            endpoint_choice = next(
                (e for e in app_databag.endpoints if e.protocol in self._protocols), None
            )
            if endpoint_choice is not None:
                endpoint_map[relation.id] = endpoint_choice

        return endpoint_map


class OtlpProvider(Object):
    """A class for publishing all supported OTLP endpoints.

    Args:
        charm: The charm instance.
        relation_name: The name of the relation to use.
    """

    _rules_cls = AlertRules

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_PROVIDER_RELATION_NAME,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._endpoints: list[OtlpEndpoint] = []
        self._topology = JujuTopology.from_charm(charm)

    def add_endpoint(
        self,
        protocol: Literal['http', 'grpc'],
        endpoint: str,
        telemetries: Sequence[Literal['logs', 'metrics', 'traces']],
    ):
        """Add an OtlpEndpoint to the list of endpoints to publish.

        Call this method after endpoint-changing events e.g. TLS and ingress.
        """
        self._endpoints.append(
            OtlpEndpoint(protocol=protocol, endpoint=endpoint, telemetries=telemetries)
        )

    def publish(self) -> None:
        """Triggers programmatically the update of the relation data."""
        if not self._charm.unit.is_leader():
            # Only the leader unit can write to app data.
            return

        databag = OtlpProviderAppData.model_validate({'endpoints': self._endpoints})
        for relation in self.model.relations[self._relation_name]:
            relation.save(databag, self._charm.app)

    def rules(self, query_type: Literal['logql', 'promql']):
        """Fetch rules for all relations of the desired query and rule types.

        This method returns all rules of the desired query and rule types
        provided by related OTLP consumer charms. These rules may be used to
        generate a rules file for each relation since the returned list of
        groups are indexed by relation ID. This method ensures rules:
            - have Juju topology from the rule's labels injected into the expr.
            - are valid using CosTool.

        Returns:
            a mapping of relation ID to a dictionary of alert rule groups
            following the OfficialRuleFileFormat from cos-lib.
        """
        rules_map: dict[str, dict[str, Any]] = {}

        rules_obj = self._rules_cls(query_type, self._topology)

        for relation in self.model.relations[self._relation_name]:
            consumer = relation.load(
                OtlpConsumerAppData, relation.app, decoder=OtlpConsumerAppData.decode_value
            )

            # get rules for the desired query type
            rules_for_type: dict[str, Any] | None = getattr(
                consumer.rules, getattr(rules_obj, 'query_type', query_type), None
            )
            if not rules_for_type:
                continue

            if not hasattr(rules_obj, 'inject_and_validate_rules'):
                continue

            result: InjectResult = rules_obj.inject_and_validate_rules(
                rules_for_type, consumer.metadata
            )
            if result.errmsg:
                if self._charm.unit.is_leader():
                    relation.data[self._charm.app]['event'] = json.dumps({'errors': result.errmsg})
                else:
                    logging.warning(
                        "Skipping write to app-level relation data 'event' on non-leader unit: %s",
                        result.errmsg,
                    )

            identifier = result.identifier
            rules = result.rules

            # If an identifier does not exist, then we should assume that something is broken
            # This could signal an issue on the cosl side
            # We should not return any rules without an identifier
            if identifier is not None:
                rules_map[identifier] = rules

        return rules_map
