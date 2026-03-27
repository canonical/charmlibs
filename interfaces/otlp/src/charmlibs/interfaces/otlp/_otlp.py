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
import re
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from cosl.juju_topology import JujuTopology
from cosl.rules import (
    HOST_METRICS_MISSING_RULE_NAME,
    InjectResult,
    Rules,
    generic_alert_groups,
)
from cosl.types import OfficialRuleFileFormat, SingleRuleFormat
from cosl.utils import LZMABase64
from ops import CharmBase
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
)

DEFAULT_REQUIRER_RELATION_NAME = 'send-otlp'
DEFAULT_PROVIDER_RELATION_NAME = 'receive-otlp'
DEFAULT_LOKI_RULES_RELATIVE_PATH = './src/loki_alert_rules'
DEFAULT_PROM_RULES_RELATIVE_PATH = './src/prometheus_alert_rules'


logger = logging.getLogger(__name__)


@dataclass
class RuleStore:
    """An API for users to provide rules of different types to the OtlpRequirer."""

    topology: JujuTopology
    logql: Rules = field(init=False)
    promql: Rules = field(init=False)

    def __post_init__(self):
        self.logql = Rules(query_type='logql', topology=self.topology)
        self.promql = Rules(query_type='promql', topology=self.topology)

    def add_logql(
        self,
        rule_dict: OfficialRuleFileFormat | SingleRuleFormat,
        *,
        group_name: str | None = None,
        group_name_prefix: str | None = None,
    ) -> 'RuleStore':
        """Add rules from dict to the existing LogQL ruleset.

        Args:
            rule_dict: a single-rule or official-rule YAML dict
            group_name: a custom group name, used only if the new rule is of single-rule format
            group_name_prefix: a custom group name prefix, used only if the new rule is of
                single-rule format
        """
        self.logql.add(rule_dict, group_name=group_name, group_name_prefix=group_name_prefix)
        return self

    def add_logql_path(self, dir_path: str | Path, *, recursive: bool = False) -> 'RuleStore':
        """Add LogQL rules from a dir path.

        All rules from files are aggregated into a data structure representing a single rule file.
        All group names are augmented with juju topology.

        Args:
            dir_path: either a rules file or a dir of rules files.
            recursive: whether to read files recursively or not (no impact if `path` is a file).
        """
        self.logql.add_path(dir_path, recursive=recursive)
        return self

    def add_promql(
        self,
        rule_dict: OfficialRuleFileFormat | SingleRuleFormat,
        *,
        group_name: str | None = None,
        group_name_prefix: str | None = None,
    ) -> 'RuleStore':
        """Add rules from dict to the existing PromQL ruleset.

        Args:
            rule_dict: a single-rule or official-rule YAML dict
            group_name: a custom group name, used only if the new rule is of single-rule format
            group_name_prefix: a custom group name prefix, used only if the new rule is of
                single-rule format
        """
        self.promql.add(rule_dict, group_name=group_name, group_name_prefix=group_name_prefix)
        return self

    def add_promql_path(self, dir_path: str | Path, *, recursive: bool = False) -> 'RuleStore':
        """Add PromQL rules from a dir path.

        All rules from files are aggregated into a data structure representing a single rule file.
        All group names are augmented with juju topology.

        Args:
            dir_path: either a rules file or a dir of rules files.
            recursive: whether to read files recursively or not (no impact if `path` is a file).
        """
        self.promql.add_path(dir_path, recursive=recursive)
        return self


class _RulesModel(BaseModel):
    """Rules of various formats (query languages) to support in the relation databag."""

    logql: OfficialRuleFileFormat = Field(
        description='LogQL alerting and recording rules, following the '
        'OfficialRuleFileFormat from cos-lib.',
        default_factory=OfficialRuleFileFormat,
    )
    promql: OfficialRuleFileFormat = Field(
        description='PromQL alerting and recording rules, following the '
        'OfficialRuleFileFormat from cos-lib.',
        default_factory=OfficialRuleFileFormat,
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

    def _duplicate_rules_per_unit(
        self,
        alert_rules: OfficialRuleFileFormat,
        rule_names_to_duplicate: list[str],
        peer_unit_names: set[str],
        is_subordinate: bool = False,
    ) -> OfficialRuleFileFormat:
        """Duplicate alert rule per unit in peer_units list.

        Args:
            alert_rules: A dictionary of rules in OfficialRuleFileFormat.
            rule_names_to_duplicate: A list of rule names to be duplicated.
            peer_unit_names: A set of charm unit names to duplicate rules for.
            is_subordinate: A boolean denoting whether the charm duplicating
                alert rules is a subordinate or not. If yes, the severity of
                the alerts in duplicate_keys needs to be set to critical.

        Returns:
            The updated rules with those specified in rule_names_to_duplicate,
            duplicated per unit in OfficialRuleFileFormat.
        """
        updated_alert_rules = copy.deepcopy(alert_rules)
        for group in updated_alert_rules.get('groups', {}):
            new_rules: list[SingleRuleFormat] = []
            for rule in group.get('rules', []):
                if rule.get('alert', '') not in rule_names_to_duplicate:
                    new_rules.append(rule)
                else:
                    for juju_unit in sorted(peer_unit_names):
                        rule_copy = copy.deepcopy(rule)
                        rule_copy.get('labels', {})['juju_unit'] = juju_unit
                        rule_copy['expr'] = self._rules.promql.tool.inject_label_matchers(
                            expression=re.sub(r'%%juju_unit%%,?', '', rule_copy['expr']),
                            topology={'juju_unit': juju_unit},
                        )
                        # If the charm is a subordinate, the severity of the alerts need to be
                        # bumped to critical.
                        rule_copy.get('labels', {})['severity'] = (
                            'critical' if is_subordinate else 'warning'
                        )
                        new_rules.append(rule_copy)
            group['rules'] = new_rules
        return updated_alert_rules

    def _inject_generic_rules(self):
        """Inject generic rules into the charm's RuleStore."""
        if self._aggregator_peer_relation_name:
            if not (
                peer_relations := self._charm.model.get_relation(
                    self._aggregator_peer_relation_name
                )
            ):
                logger.warning(
                    'Generic aggregator rules were requested, but no peer relation was found. '
                    'Ensure this charm has a peer relation named "%s" to use generic aggregator '
                    'rules.',
                    self._aggregator_peer_relation_name,
                )
            unit_names: set[str] = {self._charm.unit.name}
            if peer_relations:
                unit_names |= {unit.name for unit in peer_relations.units}
            agg_rules = self._duplicate_rules_per_unit(
                generic_alert_groups.aggregator_rules,
                rule_names_to_duplicate=[HOST_METRICS_MISSING_RULE_NAME],
                peer_unit_names=unit_names,
                is_subordinate=self._charm.meta.subordinate,
            )
            self._rules.add_promql(agg_rules, group_name_prefix=self._topology.identifier)
        else:
            self._rules.add_promql(
                generic_alert_groups.application_rules,
                group_name_prefix=self._topology.identifier,
            )

    def publish(self):
        """Triggers programmatically the update of the relation data.

        These rule sources are included when publishing:
            - Any rules provided at the instantiation of this class.
            - Generic (not specific to any charm) PromQL rules.
        """
        if not self._charm.unit.is_leader():
            # Only the leader unit can write to app data.
            return

        # Add generic rules
        self._inject_generic_rules()

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
    ) -> 'OtlpProvider':
        """Add an OtlpEndpoint to the list of endpoints to publish.

        Call this method after endpoint-changing events e.g. TLS and ingress.
        """
        self._endpoints.append(
            _OtlpEndpoint(protocol=protocol, endpoint=endpoint, telemetries=telemetries)
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

    def rules(self, query_type: Literal['logql', 'promql']) -> dict[str, OfficialRuleFileFormat]:
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
        rules_map: dict[str, OfficialRuleFileFormat] = {}
        # Instantiate Rules with topology to ensure that rules always have an identifier
        rules_obj = Rules(query_type, self._topology)
        for relation in self._charm.model.relations[self._relation_name]:
            if not relation.data[relation.app]:
                # The databags haven't initialized yet, continue
                continue

            try:
                requirer = relation.load(_OtlpRequirerAppData, relation.app)
            except ValidationError as e:
                logger.error('OTLP databag failed validation: %s', e)
                continue

            # Get rules for the desired query type
            rules_for_type: OfficialRuleFileFormat | None = getattr(
                requirer.rules, query_type, None
            )
            if not rules_for_type:
                continue

            result: InjectResult = rules_obj.inject_and_validate_rules(
                rules_for_type, requirer.metadata
            )
            if result.errmsg and self._charm.unit.is_leader():
                relation.data[self._charm.app]['event'] = json.dumps({'errors': result.errmsg})
            if result.identifier:
                rules_map[result.identifier] = result.rules

        return rules_map
