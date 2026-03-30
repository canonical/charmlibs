# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: Rules aggregation and labeling."""

import json
from typing import Any

import ops
import pytest
from cosl.rules import HOST_METRICS_MISSING_RULE_NAME
from cosl.utils import LZMABase64
from ops import testing
from ops.testing import Model, PeerRelation, Relation, State

from charmlibs.interfaces.otlp._otlp import DEFAULT_PROVIDER_RELATION_NAME as RECEIVE
from charmlibs.interfaces.otlp._otlp import DEFAULT_REQUIRER_RELATION_NAME as SEND
from charmlibs.interfaces.otlp._otlp import (
    OtlpProvider,
    OtlpRequirer,
    _OtlpRequirerAppData,
    _RulesModel,
)
from conftest import (
    PEERS_ENDPOINT,
    SINGLE_LOGQL_ALERT,
    SINGLE_LOGQL_RECORD,
    SINGLE_PROMQL_ALERT,
    SINGLE_PROMQL_RECORD,
)

MODEL_NAME = 'foo-model'
MODEL_UUID = 'f4d59020-c8e7-4053-8044-a2c1e5591c7f'
MODEL_SHORT_UUID = 'f4d59020'
MODEL = Model(MODEL_NAME, uuid=MODEL_UUID)


def _decompress(rules: str | None) -> dict[str, Any]:
    if not rules:
        return {}
    return json.loads(LZMABase64.decompress(rules))


def test_new_rule_is_ignored_by_databag_model():
    # GIVEN the requirer offers a new rule type
    # * the provider does not support this new rule type
    # WHEN validating the requirer databag model, which the provider uses to access rules
    # THEN the validation succeeds
    requirer_databag = _OtlpRequirerAppData.model_validate({
        'rules': {'promql': {}, 'new_rule': {}},
        'metadata': {},
    })
    assert requirer_databag
    assert isinstance(requirer_databag.rules, _RulesModel)
    # AND the new rule type is ignored
    assert 'new_rule' not in requirer_databag.rules.model_dump()


def test_missing_rule_type_defaults():
    # GIVEN no rules or metadata is provided
    # WHEN validating the requirer databag model
    # THEN the validation succeeds
    requirer_databag = _OtlpRequirerAppData.model_validate({'rules': {}, 'metadata': {}})
    assert requirer_databag
    assert isinstance(requirer_databag.rules, _RulesModel)
    # AND the rule model is created
    assert requirer_databag.rules.model_dump().keys() == _RulesModel.model_fields.keys()


def test_rules_compression(otlp_requirer_ctx: testing.Context[ops.CharmBase]):
    # GIVEN a send-otlp relation
    state = State(relations=[Relation(SEND)], leader=True)

    # WHEN the update_status event is fired
    state_out = otlp_requirer_ctx.run(otlp_requirer_ctx.on.update_status(), state=state)
    for relation in list(state_out.relations):
        rules = relation.local_app_data.get('rules', None)
        assert rules is not None

        # THEN the databag contains a compressed set of rules
        assert isinstance(rules, str)
        assert rules.startswith('"/')  # JSON-encoded LMZABase64 string
        decompressed = _decompress(json.loads(rules))
        assert decompressed
        assert isinstance(decompressed, dict)
        assert set(_RulesModel.model_fields.keys()).issubset(decompressed.keys())


@pytest.mark.parametrize('subordinate', [True, False])
def test_duplicate_rules_per_unit(
    otlp_requirer_ctx: testing.Context[ops.CharmBase], subordinate: bool
):
    with otlp_requirer_ctx(otlp_requirer_ctx.on.update_status(), state=State(leader=True)) as mgr:
        # GIVEN any charm
        # WHEN the OtlpRequirer is initialized
        # * generic aggregator rules are desired
        # * no peer relation name is provided
        result = OtlpRequirer(mgr.charm)._duplicate_rules_per_unit(
            alert_rules={
                'groups': [
                    {
                        'name': 'AggregatorHostHealth',
                        'rules': [
                            {
                                'alert': HOST_METRICS_MISSING_RULE_NAME,
                                'expr': 'absent(up)',
                                'labels': {'severity': 'warning'},
                            },
                            {
                                'alert': 'AggregatorMetricsMissing',
                                'expr': 'absent(up)',
                                'labels': {'severity': 'critical'},
                            },
                        ],
                    }
                ]
            },
            peer_unit_names={'unit/0', 'unit/1'},
            rule_names_to_duplicate=[HOST_METRICS_MISSING_RULE_NAME],
            is_subordinate=subordinate,
        )
        # THEN the rules are duplicated per unit, with juju_unit in the expr and labels
        groups = result.get('groups', [])
        for group in groups:
            rules = group.get('rules', [])
            severity = 'critical' if subordinate else 'warning'
            assert rules == [
                {
                    'alert': HOST_METRICS_MISSING_RULE_NAME,
                    'expr': 'absent(up{juju_unit="unit/0"})',
                    'labels': {'severity': severity, 'juju_unit': 'unit/0'},
                },
                {
                    'alert': HOST_METRICS_MISSING_RULE_NAME,
                    'expr': 'absent(up{juju_unit="unit/1"})',
                    'labels': {'severity': severity, 'juju_unit': 'unit/1'},
                },
                {
                    'alert': 'AggregatorMetricsMissing',
                    'expr': 'absent(up)',
                    'labels': {'severity': 'critical'},
                },
            ]


@pytest.mark.parametrize(
    'otlp_requirer_ctx,is_aggregator',
    [
        pytest.param(True, True, id='aggregator'),
        pytest.param(False, False, id='non-aggregator'),
    ],
    indirect=['otlp_requirer_ctx'],
)
def test_generic_rule_injection(
    otlp_requirer_ctx: testing.Context[ops.CharmBase], is_aggregator: bool
):
    # GIVEN a send-otlp relation
    # * a peers relation
    peers = PeerRelation(endpoint=PEERS_ENDPOINT)
    state = State(relations=[peers, Relation(SEND)], leader=True, model=MODEL)

    # WHEN the update_status event is fired
    state_out = otlp_requirer_ctx.run(otlp_requirer_ctx.on.update_status(), state=state)
    for relation in list(state_out.relations):
        if relation.endpoint != SEND:
            continue

        # THEN if the charm is an aggregator, generic rules are injected into the databag
        # AND the rules in the databag are decompressed
        decompressed = _decompress(relation.local_app_data.get('rules'))
        assert decompressed
        promql_groups = decompressed.get('promql', {}).get('groups', [])
        assert promql_groups

        # THEN the generic promql rule is in the databag
        base_rule_name = f'{MODEL_NAME.replace("-", "_")}_{MODEL_SHORT_UUID}_otlp_requirer'
        agg_rule = f'{base_rule_name}_AggregatorHostHealth_rules'
        app_rule = f'{base_rule_name}_HostHealth_rules'
        promql_group_names = [g.get('name') for g in promql_groups]
        if is_aggregator:
            assert agg_rule in promql_group_names
            assert app_rule not in promql_group_names
        else:
            assert app_rule in promql_group_names
            assert agg_rule not in promql_group_names


def test_metadata(otlp_requirer_ctx: testing.Context[ops.CharmBase]):
    # GIVEN a send-otlp relation
    state = State(relations=[Relation(SEND)], leader=True, model=MODEL)

    # WHEN the update_status event is fired
    state_out = otlp_requirer_ctx.run(otlp_requirer_ctx.on.update_status(), state=state)
    for relation in list(state_out.relations):
        # THEN the requirer adds its own metadata to the databag
        assert json.loads(relation.local_app_data['metadata']) == {
            'model': MODEL_NAME,
            'model_uuid': MODEL_UUID,
            'application': 'otlp-requirer',
            'unit': 'otlp-requirer/0',
            'charm_name': 'otlp-requirer',
        }


@pytest.mark.parametrize(
    'metadata',
    [
        {},
        {
            'model': MODEL_NAME,
            'model_uuid': MODEL_UUID,
            'application': 'otlp-requirer',
            'charm_name': 'otlp-requirer',
            'unit': 'otlp-requirer/0',
        },
    ],
)
def test_provider_rules(
    otlp_provider_ctx: testing.Context[ops.CharmBase], metadata: dict[str, Any]
):
    # GIVEN a requirer offers unlabeled rules (of various types) in the databag
    rules = {
        'logql': {
            'groups': [
                {'name': 'test_logql_alert', 'rules': [SINGLE_LOGQL_ALERT]},
                {'name': 'test_logql_record', 'rules': [SINGLE_LOGQL_RECORD]},
            ]
        },
        'promql': {
            'groups': [
                {'name': 'test_promql_alert', 'rules': [SINGLE_PROMQL_ALERT]},
                {'name': 'test_promql_record', 'rules': [SINGLE_PROMQL_RECORD]},
            ]
        },
    }
    receiver = Relation(
        RECEIVE, remote_app_data={'rules': json.dumps(rules), 'metadata': json.dumps(metadata)}
    )
    state = State(leader=True, relations=[receiver], model=MODEL)
    with otlp_provider_ctx(otlp_provider_ctx.on.update_status(), state=state) as mgr:
        # WHEN the provider aggregates the rules from the databag
        rule_store = OtlpProvider(mgr.charm, RECEIVE).rules[receiver.id]
        logql = rule_store.logql.as_dict()
        promql = rule_store.promql.as_dict()
        # THEN LogQL and PromQL rules exist in the RuleStore
        assert logql
        assert promql
        for result in [logql, promql]:
            app = metadata['application'] if metadata else 'otlp-provider'
            charm = metadata['charm_name'] if metadata else 'otlp-provider'
            groups = result.get('groups', [])
            assert groups
            for group in groups:
                for rule in group.get('rules', []):
                    # AND the rules are labeled with the provider's topology
                    assert rule.get('labels', {}).get('juju_model') == MODEL_NAME
                    assert rule.get('labels', {}).get('juju_model_uuid') == MODEL_UUID
                    assert rule.get('labels', {}).get('juju_application') == app
                    assert rule.get('labels', {}).get('juju_charm') == charm

                    # AND the expressions are labeled
                    assert f'juju_model="{MODEL_NAME}"' in rule['expr']
                    assert f'juju_model_uuid="{MODEL_UUID}"' in rule['expr']
                    assert f'juju_application="{app}"' in rule['expr']
