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

import binascii
import copy
import hashlib
import json
import logging
from collections import OrderedDict
from collections.abc import Sequence
from lzma import LZMAError
from pathlib import Path
from typing import Any, Literal

from cosl.juju_topology import JujuTopology
from cosl.rules import AlertRules, InjectResult, generic_alert_groups
from cosl.types import OfficialRuleFileFormat
from cosl.utils import LZMABase64
from ops import CharmBase
from ops.framework import Object
from pydantic import BaseModel, Field, ValidationError

DEFAULT_REQUIRER_RELATION_NAME = 'send-otlp'
DEFAULT_PROVIDER_RELATION_NAME = 'receive-otlp'
DEFAULT_LOKI_RULES_RELATIVE_PATH = './src/loki_alert_rules'
DEFAULT_PROM_RULES_RELATIVE_PATH = './src/prometheus_alert_rules'


logger = logging.getLogger(__name__)


class RulesModel(BaseModel):
    """Rules of various formats (query languages) to support in the relation databag."""

    logql: OfficialRuleFileFormat = Field(
        description='LogQL alerting and recording rules, following the '
        'OfficialRuleFileFormat from cos-lib.'
    )
    promql: OfficialRuleFileFormat = Field(
        description='PromQL alerting and recording rules, following the '
        'OfficialRuleFileFormat from cos-lib.'
    )


class OtlpEndpoint(BaseModel):
    """A pydantic model for a single OTLP endpoint."""

    protocol: str = Field(
        description='Transport protocol used to send telemetry data to this endpoint.'
    )
    endpoint: str = Field(description="URL of the OTLP endpoint (e.g. 'http://collector:4318').")
    telemetries: Sequence[str] = Field(
        description='Telemetry signal types accepted by this endpoint.'
    )


class OtlpProviderAppData(BaseModel):
    """A pydantic model for the OTLP provider's app databag."""

    endpoints: list[OtlpEndpoint] = Field(
        description='List of OTLP endpoints exposed by the provider.'
    )


class OtlpRequirerAppData(BaseModel):
    """A pydantic model for the OTLP requirer's app databag.

    The rules are compressed when saved to databag to avoid hitting databag
    size limits for large deployments. An admin can decode the rules using the
    following command:
    ```bash
    <rules-from-show-unit> | base64 -d | xz -d | jq
    ```
    """

    rules: RulesModel | str = Field(
        description='Rules to be forwarded to the provider.'
        ' Stored as an LZMA-compressed, base64-encoded JSON string to reduce payload size.'
    )
    metadata: OrderedDict[str, str] = Field(
        description='Juju topology of the requirer charm (e.g. model, app, unit),'
        ' used to label rule expressions and alert routing.'
    )

    @staticmethod
    def decode_value(json_str: str) -> Any:
        """Decode a relation databag value from its serialized string form.

        Attempts to decompress and deserialize the value as a ``RulesModel``, falls back to
        plain JSON deserialization.
        """
        try:
            decompressed = LZMABase64.decompress(json_str)
            return RulesModel.model_validate(json.loads(decompressed))
        except (LZMAError, binascii.Error):
            return json.loads(json_str)

    @staticmethod
    def encode_value(obj: Any) -> str:
        """Encode relation data values into a string.

        Rules are LZMA-compressed and base64-encoded to reduce content size for larger deployments.
        Other data is serialized into a JSON formatted str.
        """
        try:
            RulesModel.model_validate(obj)
            return LZMABase64.compress(json.dumps(obj, sort_keys=True))
        except ValidationError:
            return json.dumps(obj, sort_keys=True)


class OtlpRequirer(Object):
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

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_REQUIRER_RELATION_NAME,
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
        self._loki_rules_path: str | Path = loki_rules_path
        self._prom_rules_path: str | Path = prometheus_rules_path

    def _filter_endpoints(self, endpoints: list[OtlpEndpoint]) -> list[OtlpEndpoint]:
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
        charm's filesystem and providing those paths to the OtlpRequirer
        constructor.
        """
        if not self._charm.unit.is_leader():
            # Only the leader unit can write to app data.
            return

        # Define the rule types
        loki_rules = AlertRules(query_type='logql', topology=self._topology)
        prom_rules = AlertRules(query_type='promql', topology=self._topology)

        # Add rules
        prom_rules.add(
            copy.deepcopy(generic_alert_groups.aggregator_rules),
            group_name_prefix=self._topology.identifier,
        )
        loki_rules.add_path(self._loki_rules_path, recursive=True)
        prom_rules.add_path(self._prom_rules_path, recursive=True)

        # Publish to databag
        databag = OtlpRequirerAppData.model_validate({
            'rules': {'logql': loki_rules.as_dict(), 'promql': prom_rules.as_dict()},
            'metadata': self._topology.as_dict(),
        })
        for relation in self.model.relations[self._relation_name]:
            relation.save(databag, self._charm.app, encoder=OtlpRequirerAppData.encode_value)

    @property
    def endpoints(self) -> dict[int, OtlpEndpoint]:
        """Return a mapping of relation ID to OTLP endpoint.

        For each remote's list of OtlpEndpoints, the requirer filters out
        unsupported endpoints and telemetries. If there are multiple supported
        endpoints, the requirer chooses the first available endpoint in the
        list. This allows providers to specify multiple endpoints with
        different protocols and/or telemetry types and the requirer can choose
        one based on its own capabilities. For example, a provider may specify
        both an HTTP and gRPC endpoint, and a requirer that only supports HTTP
        will choose the HTTP endpoint.
        """
        endpoint_map: dict[int, OtlpEndpoint] = {}
        for relation in self.model.relations[self._relation_name]:
            provider = relation.load(OtlpProviderAppData, relation.app)
            endpoints = self._filter_endpoints(provider.endpoints)
            if endpoints:
                endpoint_map[relation.id] = endpoints[0]

        return endpoint_map


class OtlpProvider(Object):
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
        provided by related OTLP requirer charms. These rules may be used to
        generate a rules file for each relation since the returned list of
        groups are indexed by relation ID. This method ensures rules:

            - have Juju topology from the rule's labels injected into the expr.
            - are valid using CosTool.

        Returns:
            a mapping of relation ID to a dictionary of alert rule groups
            following the OfficialRuleFileFormat from cos-lib.
        """
        rules_map: dict[str, dict[str, Any]] = {}
        rules_obj = AlertRules(query_type, self._topology)
        for relation in self.model.relations[self._relation_name]:
            requirer = relation.load(
                OtlpRequirerAppData, relation.app, decoder=OtlpRequirerAppData.decode_value
            )

            # Get rules for the desired query type
            rules_for_type: dict[str, Any] | None = getattr(requirer.rules, query_type, None)
            if not rules_for_type:
                continue

            result: InjectResult = rules_obj.inject_and_validate_rules(
                rules_for_type, requirer.metadata
            )
            if result.errmsg and self._charm.unit.is_leader():
                relation.data[self._charm.app]['event'] = json.dumps({'errors': result.errmsg})

            # If an identifier does not exist, we generate a deterministic hash
            # derived from the rules content so the rules can still be recorded
            # for this relation. This avoids dropping rules when the upstream
            # requirer metadata does not provide an identifier.
            identifier = result.identifier
            if identifier is None:
                try:
                    rules_json = json.dumps(result.rules, sort_keys=True)
                except (TypeError, ValueError):
                    rules_json = repr(result.rules)

                content_hash = hashlib.sha256(rules_json.encode('utf-8')).hexdigest()[:12]
                identifier = content_hash
                logger.debug(
                    'No identifier from injected rules for relation %s; generated hash %s',
                    relation.id,
                    identifier,
                )

            rules_map[identifier] = result.rules

        return rules_map
