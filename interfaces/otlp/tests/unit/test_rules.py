# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: Rules aggregation and forwarding."""

import json
from typing import Any

import ops
import pytest
from cosl.utils import LZMABase64
from ops import testing
from ops.testing import Model, Relation, State

from charmlibs.otlp import (
    OtlpConsumerAppData,
    RulesModel,
)
from helpers import patch_cos_tool_path

OTELCOL_LABELS = {
    'juju_model': 'otelcol',
    'juju_model_uuid': 'f4d59020-c8e7-4053-8044-a2c1e5591c7f',
    'juju_application': 'opentelemetry-collector-k8s',
    'juju_charm': 'opentelemetry-collector-k8s',
}
LOGQL_ALERT = {
    'name': 'otelcol_f4d59020_charm_x_foo_alerts',
    'rules': [
        {
            'alert': 'HighLogVolume',
            'expr': 'count_over_time({job=~".+"}[30s]) > 100',
            'labels': {'severity': 'high'},
        },
    ],
}
LOGQL_RECORD = {
    'name': 'otelcol_f4d59020_charm_x_foobar_alerts',
    'rules': [
        {
            'record': 'log:error_rate:rate5m',
            'expr': 'sum by (service) (rate({job=~".+"} | json | level="error" [5m]))',
            'labels': {'severity': 'high'},
        }
    ],
}
PROMQL_ALERT = {
    'name': 'otelcol_f4d59020_charm_x_bar_alerts',
    'rules': [
        {
            'alert': 'Workload Missing',
            'expr': 'up{job=~".+"} == 0',
            'for': '0m',
            'labels': {'severity': 'critical'},
        },
    ],
}
PROMQL_RECORD = {
    'name': 'otelcol_f4d59020_charm_x_barfoo_alerts',
    'rules': [
        {
            'record': 'code:prometheus_http_requests_total:sum',
            'expr': 'sum by (code) (prometheus_http_requests_total{job=~".+"})',
            'labels': {'severity': 'high'},
        }
    ],
}
ALL_RULES = {
    'logql': {'groups': [LOGQL_ALERT, LOGQL_RECORD]},
    'promql': {'groups': [PROMQL_ALERT, PROMQL_RECORD]},
}

METADATA = {
    'model': 'otelcol',
    'model_uuid': 'f4d59020-c8e7-4053-8044-a2c1e5591c7f',
    'application': 'opentelemetry-collector-k8s',
    'charm': 'opentelemetry-collector-k8s',
    'unit': 'opentelemetry-collector-k8s/0',
}


def _decompress(rules: str | None) -> dict[str, Any]:
    if not rules:
        return {}
    return json.loads(LZMABase64.decompress(rules))


@pytest.mark.parametrize(
    'valid_compression, compressed_rules',
    [
        (True, LZMABase64.compress(json.dumps(ALL_RULES, sort_keys=True))),
        (False, '/Td6WFoAAATm1rRGAgAhARYAAAB0L+Wj4AM4AWFdAD2I'),
    ],
    ids=['valid compression', 'invalid compression'],
)
def test_forwarded_rules_compression(
    otlp_dual_ctx: testing.Context[ops.CharmBase],
    valid_compression: bool,
    compressed_rules: str,
) -> None:
    # GIVEN receive-otlp and send-otlp relations
    databag: dict[str, Any] = {'rules': compressed_rules, 'metadata': json.dumps(METADATA)}
    receiver = Relation('receive-otlp', remote_app_data=databag)
    sender_1 = Relation('send-otlp', remote_app_data={'endpoints': '[]'})
    sender_2 = Relation('send-otlp', remote_app_data={'endpoints': '[]'})
    state = State(
        relations=[receiver, sender_1, sender_2],
        leader=True,
        model=Model('otelcol', uuid='f4d59020-c8e7-4053-8044-a2c1e5591c7f'),
    )

    # WHEN any event executes the reconciler
    with patch_cos_tool_path():
        state_out = otlp_dual_ctx.run(otlp_dual_ctx.on.update_status(), state=state)

    for relation in list(state_out.relations):
        if relation.endpoint != 'send-otlp':
            continue
        raw_rules = relation.local_app_data.get('rules')

        # THEN the databag contains a compressed set of rules
        assert isinstance(raw_rules, str)
        assert raw_rules.startswith('/')
        decompressed = _decompress(raw_rules)
        assert decompressed
        assert isinstance(decompressed, dict)
        actual_groups = decompressed.get('logql', {}).get('groups', [])
        if not valid_compression:
            # THEN the decompressed databag contains no rules
            assert not actual_groups
        else:
            # THEN the decompressed databag contains rules
            assert actual_groups
            actual_group_names: set[str] = set()
            for group in actual_groups:
                name = group.get('name')
                if isinstance(name, str):
                    actual_group_names.add(name)
            expected_groups = ALL_RULES.get('logql', {}).get('groups', [])
            expected_group_names: set[str] = set()
            for group in expected_groups:
                name = group.get('name')
                if isinstance(name, str):
                    expected_group_names.add(name)
            assert actual_group_names == expected_group_names


@pytest.mark.parametrize(
    'forwarding_enabled, rules, expected_group_counts',
    [
        # format , databag_groups, generic_groups, total
        # logql  , (2)           , (0)           , (2)
        # promql , (2)           , (1)           , (3)
        (
            True,
            {
                'logql': {'groups': [LOGQL_ALERT, LOGQL_RECORD]},
                'promql': {'groups': [PROMQL_ALERT, PROMQL_RECORD]},
            },
            {'logql': 2, 'promql': 3},
        ),
        # format , databag_groups, generic_groups, total
        # logql  , (0)           , (0)           , (0)
        # promql , (2)           , (1)           , (3)
        (
            True,
            {'logql': {}, 'promql': {'groups': [PROMQL_ALERT, PROMQL_RECORD]}},
            {'logql': 0, 'promql': 3},
        ),
        # format , databag_groups, generic_groups, total
        # logql  , (2)           , (0)           , (2)
        # promql , (0)           , (1)           , (1)
        (
            True,
            {'logql': {'groups': [LOGQL_ALERT, LOGQL_RECORD]}, 'promql': {}},
            {'logql': 2, 'promql': 1},
        ),
    ],
)
def test_forwarding_otlp_rule_counts(
    otlp_dual_ctx: testing.Context[ops.CharmBase],
    forwarding_enabled: bool,
    rules: dict[str, Any],
    expected_group_counts: dict[str, int],
) -> None:
    # GIVEN forwarding of rules is enabled
    # * a receive-otlp with rules in the databag
    # * two send-otlp relations
    databag: dict[str, Any] = {'rules': json.dumps(rules), 'metadata': json.dumps(METADATA)}
    receiver = Relation('receive-otlp', remote_app_data=databag)
    sender_1 = Relation('send-otlp', remote_app_data={'endpoints': '[]'})
    sender_2 = Relation('send-otlp', remote_app_data={'endpoints': '[]'})
    state = State(
        relations=[receiver, sender_1, sender_2],
        leader=True,
        model=Model('otelcol', uuid='f4d59020-c8e7-4053-8044-a2c1e5591c7f'),
        config={'forward_alert_rules': forwarding_enabled},
    )

    # WHEN any event executes the reconciler
    state_out = otlp_dual_ctx.run(otlp_dual_ctx.on.update_status(), state=state)

    for relation in list(state_out.relations):
        if relation.endpoint != 'send-otlp':
            continue

        decompressed = _decompress(relation.local_app_data.get('rules'))
        assert decompressed
        consumer_databag: OtlpConsumerAppData = OtlpConsumerAppData.model_validate({
            'rules': decompressed,
            'metadata': {},
        })

        # THEN all expected rules exist in the databag
        # * databag_groups are included/forwarded
        assert isinstance(consumer_databag.rules, RulesModel)

        assert (
            len(consumer_databag.rules.logql.get('groups', [])) == expected_group_counts['logql']
        )
        assert (
            len(consumer_databag.rules.promql.get('groups', [])) == expected_group_counts['promql']
        )
