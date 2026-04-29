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

"""Rules-related logic for the OTLP library."""

import copy
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from cosl.juju_topology import JujuTopology
from cosl.rules import HOST_METRICS_MISSING_RULE_NAME, CosTool, Rules, generic_alert_groups
from cosl.types import OfficialRuleFileFormat, SingleRuleFormat
from ops import CharmBase
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = [
    'RuleStore',
    '_RulesModel',
    'duplicate_rules_per_unit',
    'inject_generic_rules',
]


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

    def combine(self, other: 'RuleStore') -> 'RuleStore':
        """Combine rules from another RuleStore with this RuleStore."""
        if other_logql := other.logql.as_dict():
            self.logql.add(other_logql)
        if other_promql := other.promql.as_dict():
            self.promql.add(other_promql)
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


def duplicate_rules_per_unit(
    alert_rules: OfficialRuleFileFormat,
    rule_names_to_duplicate: list[str],
    peer_unit_names: set[str],
    rules_tool: CosTool,
    is_subordinate: bool = False,
) -> OfficialRuleFileFormat:
    """Duplicate alert rule per unit in peer_units list.

    Args:
        alert_rules: A dictionary of rules in OfficialRuleFileFormat.
        rule_names_to_duplicate: A list of rule names to be duplicated.
        peer_unit_names: A set of charm unit names to duplicate rules for.
        rules_tool: A Rules instance whose ``tool`` is used to inject label matchers.
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
                    rule_copy['expr'] = rules_tool.inject_label_matchers(
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


def inject_generic_rules(
    charm: CharmBase,
    rules: RuleStore,
    topology: JujuTopology,
    aggregator_peer_relation_name: str | None = None,
) -> RuleStore:
    """Inject generic rules into the charm's RuleStore.

    Args:
        charm: The charm instance.
        rules: The RuleStore to inject generic rules into.
        topology: The JujuTopology of the charm.
        aggregator_peer_relation_name: Name of the peers relation of this
            charm. When provided, generic aggregator rules are used instead
            of application-level rules.
    """
    rules_copy = copy.deepcopy(rules)
    if aggregator_peer_relation_name:
        if not (peer_relations := charm.model.get_relation(aggregator_peer_relation_name)):
            logger.warning(
                'Generic aggregator rules were requested, but no peer relation was found. '
                'Ensure this charm has a peer relation named "%s" to use generic aggregator '
                'rules.',
                aggregator_peer_relation_name,
            )
        unit_names: set[str] = {charm.unit.name}
        if peer_relations:
            unit_names |= {unit.name for unit in peer_relations.units}
        agg_rules = duplicate_rules_per_unit(
            generic_alert_groups.aggregator_rules,
            rule_names_to_duplicate=[HOST_METRICS_MISSING_RULE_NAME],
            peer_unit_names=unit_names,
            rules_tool=rules_copy.promql.tool,
            is_subordinate=charm.meta.subordinate,
        )
        rules_copy.add_promql(agg_rules, group_name_prefix=topology.identifier)
    else:
        rules_copy.add_promql(
            generic_alert_groups.application_rules,
            group_name_prefix=topology.identifier,
        )
    return rules_copy


def inject_extra_labels_into_rules(
    rules: RuleStore, extra_alert_labels: dict[str, str]
) -> RuleStore:
    """Return a copy of the rules dict with extra labels injected."""
    if not extra_alert_labels:
        return rules
    rules_copy = copy.deepcopy(rules)
    for rule_groups in [rules_copy.logql.as_dict(), rules_copy.promql.as_dict()]:
        for group in rule_groups.get('groups', []):
            for rule in group.get('rules', []):
                rule.setdefault('labels', {}).update(extra_alert_labels)
    return rules_copy
