# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: Rules aggregation and forwarding."""

import json
from typing import Any, Dict, Optional

import pytest
from cosl.utils import LZMABase64
from ops.testing import Model, Relation, State

from charmlibs.otlp import (
    OtlpConsumerAppData,
    RulesModel,
)

OTELCOL_LABELS = {
    "juju_model": "otelcol",
    "juju_model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
    "juju_application": "opentelemetry-collector-k8s",
    "juju_charm": "opentelemetry-collector-k8s",
}
LOGQL_ALERT = {
    "name": "otelcol_f4d59020_charm_x_foo_alerts",
    "rules": [
        {
            "alert": "HighLogVolume",
            "expr": 'count_over_time({job=~".+"}[30s]) > 100',
            "labels": {"severity": "high"},
        },
    ],
}
LOGQL_RECORD = {
    "name": "otelcol_f4d59020_charm_x_foobar_alerts",
    "rules": [
        {
            "record": "log:error_rate:rate5m",
            "expr": 'sum by (service) (rate({job=~".+"} | json | level="error" [5m]))',
            "labels": {"severity": "high"},
        }
    ],
}
PROMQL_ALERT = {
    "name": "otelcol_f4d59020_charm_x_bar_alerts",
    "rules": [
        {
            "alert": "Workload Missing",
            "expr": 'up{job=~".+"} == 0',
            "for": "0m",
            "labels": {"severity": "critical"},
        },
    ],
}
PROMQL_RECORD = {
    "name": "otelcol_f4d59020_charm_x_barfoo_alerts",
    "rules": [
        {
            "record": "code:prometheus_http_requests_total:sum",
            "expr": 'sum by (code) (prometheus_http_requests_total{job=~".+"})',
            "labels": {"severity": "high"},
        }
    ],
}
ALL_RULES = {
    "logql": {"groups": [LOGQL_ALERT, LOGQL_RECORD]},
    "promql": {"groups": [PROMQL_ALERT, PROMQL_RECORD]},
}


def _decompress(rules: str) -> dict:
    return json.loads(LZMABase64.decompress(rules))


def _get_group_by_name(rules: Optional[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    if rules is None:
        return None
    for group in rules.get("groups", []):
        if group.get("name") == name:
            return group
    return None


def _rules_have_labels(groups: Dict[str, Any], labels: Dict[str, Any]) -> bool:
    assert groups
    assert labels
    for rule in groups.get("rules", []):
        if "labels" not in rule:
            return False
        for key, value in labels.items():
            if rule["labels"].get(key) != value:
                return False
    return True


@pytest.mark.parametrize(
    "valid_compression, compressed_rules",
    [
        (True, LZMABase64.compress(json.dumps(ALL_RULES, sort_keys=True))),
        (False, "/Td6WFoAAATm1rRGAgAhARYAAAB0L+Wj4AM4AWFdAD2I"),
    ],
)
def test_forwarded_rules_compression(
    ctx,
    otelcol_container,
    valid_compression,
    compressed_rules,
):
    # GIVEN receive-otlp and send-otlp relations
    databag = {"rules": compressed_rules, "metadata": "{}"}
    receiver = Relation("receive-otlp", remote_app_data=databag)
    sender_1 = Relation("send-otlp", remote_app_data={"endpoints": "[]"})
    sender_2 = Relation("send-otlp", remote_app_data={"endpoints": "[]"})
    state = State(
        relations=[receiver, sender_1, sender_2],
        leader=True,
        containers=otelcol_container,
        model=Model("otelcol", uuid="f4d59020-c8e7-4053-8044-a2c1e5591c7f"),
    )

    # WHEN any event executes the reconciler
    state_out = ctx.run(ctx.on.update_status(), state=state)

    for relation in list(state_out.relations):
        if relation.endpoint != "send-otlp":
            continue
        raw_rules = relation.local_app_data.get("rules")

        # THEN the databag contains a compressed set of rules
        assert isinstance(raw_rules, str)
        assert raw_rules.startswith("/")
        assert (decompressed := _decompress(raw_rules))
        assert isinstance(decompressed, dict)
        actual_groups = decompressed.get("logql", {}).get("groups", [])
        if not valid_compression:
            # THEN the decompressed databag contains no rules
            assert not actual_groups
        else:
            # THEN the decompressed databag contains rules
            assert actual_groups
            assert (actual_group_names := {group.get("name") for group in actual_groups})
            assert (expected_groups := ALL_RULES.get("logql", {}).get("groups", []))
            assert (expected_group_names := {group.get("name") for group in expected_groups})
            assert actual_group_names == expected_group_names


@pytest.mark.parametrize(
    "forwarding_enabled, rules, expected_group_counts",
    [
        # format , databag_groups, generic_groups, bundled_groups, total
        # logql  , (2)           , (0)           , (0)           , (0)
        # promql , (2)           , (1)           , (3)           , (4)
        (
            False,
            {
                "logql": {"groups": [LOGQL_ALERT, LOGQL_RECORD]},
                "promql": {"groups": [PROMQL_ALERT, PROMQL_RECORD]},
            },
            {"logql": 0, "promql": 4},
        ),
        # format , databag_groups, generic_groups, bundled_groups, total
        # logql  , (2)           , (0)           , (0)           , (2)
        # promql , (2)           , (1)           , (3)           , (6)
        (
            True,
            {
                "logql": {"groups": [LOGQL_ALERT, LOGQL_RECORD]},
                "promql": {"groups": [PROMQL_ALERT, PROMQL_RECORD]},
            },
            {"logql": 2, "promql": 6},
        ),
        # format , databag_groups, generic_groups, bundled_groups, total
        # logql  , (0)           , (0)           , (0)           , (0)
        # promql , (2)           , (1)           , (3)           , (6)
        (
            True,
            {"logql": {}, "promql": {"groups": [PROMQL_ALERT, PROMQL_RECORD]}},
            {"logql": 0, "promql": 6},
        ),
        # format , databag_groups, generic_groups, bundled_groups, total
        # logql  , (2)           , (0)           , (0)           , (2)
        # promql , (0)           , (1)           , (3)           , (4)
        (
            True,
            {"logql": {"groups": [LOGQL_ALERT, LOGQL_RECORD]}, "promql": {}},
            {"logql": 2, "promql": 4},
        ),
    ],
)
def test_forwarding_otlp_rule_counts(
    ctx, otelcol_container, forwarding_enabled, rules, expected_group_counts
):
    # GIVEN forwarding of rules is enabled
    # * a receive-otlp with rules in the databag
    # * two send-otlp relations
    databag = {"rules": json.dumps(rules), "metadata": "{}"}
    receiver = Relation("receive-otlp", remote_app_data=databag)
    sender_1 = Relation("send-otlp", remote_app_data={"endpoints": "[]"})
    sender_2 = Relation("send-otlp", remote_app_data={"endpoints": "[]"})
    state = State(
        relations=[receiver, sender_1, sender_2],
        leader=True,
        containers=otelcol_container,
        model=Model("otelcol", uuid="f4d59020-c8e7-4053-8044-a2c1e5591c7f"),
        config={"forward_alert_rules": forwarding_enabled},
    )

    # WHEN any event executes the reconciler
    state_out = ctx.run(ctx.on.update_status(), state=state)

    for relation in list(state_out.relations):
        if relation.endpoint != "send-otlp":
            continue
        assert (decompressed := _decompress(relation.local_app_data.get("rules")))
        databag = OtlpConsumerAppData.model_validate({"rules": decompressed, "metadata": {}})

        # THEN all expected rules exist in the databag
        # * databag_groups are included/forwarded
        assert isinstance(databag.rules, RulesModel)
        assert len(databag.rules.logql.get("groups", [])) == expected_group_counts["logql"]
        assert len(databag.rules.promql.get("groups", [])) == expected_group_counts["promql"]


@pytest.mark.parametrize(
    "metadata, expected_labels",
    [
        (
            # No metadata
            {},
            OTELCOL_LABELS,
        ),
        (
            # Missing mandatory "application" metadata field
            {
                "model": "otelcol",
                "model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
                # "application": "intentionally commented out",
            },
            OTELCOL_LABELS,
        ),
        (
            # Minimal metadata
            {
                "model": "otelcol",
                "model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
                "application": "foo",
            },
            {
                "juju_model": "otelcol",
                "juju_model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
                "juju_application": "foo",
                "juju_unit": "",
                "juju_charm": "",
            },
        ),
        (
            # All metadata fields
            {
                "model": "otelcol",
                "model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
                "application": "foo",
                "unit": "0",
                "charm_name": "foo",
            },
            {
                "juju_model": "otelcol",
                "juju_model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
                "juju_application": "foo",
                "juju_unit": "0",
                "juju_charm": "foo",
            },
        ),
        (
            # Invalid metadata field
            {
                "model": "otelcol",
                "model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
                "application": "foo",
                "does_not_exist": "foo",
            },
            {
                "juju_model": "otelcol",
                "juju_model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
                "juju_application": "foo",
                "juju_unit": "",
                "juju_charm": "",
            },
        ),
    ],
)
def test_forwarded_rules_have_topology(ctx, otelcol_container, metadata, expected_labels):
    # GIVEN receive-otlp and send-otlp relations
    rules = {
        "logql": {"groups": [LOGQL_ALERT, LOGQL_RECORD]},
        "promql": {"groups": [PROMQL_ALERT, PROMQL_RECORD]},
    }
    databag = {"rules": json.dumps(rules), "metadata": json.dumps(metadata)}
    receiver = Relation("receive-otlp", remote_app_data=databag)
    sender_1 = Relation("send-otlp", remote_app_data={"endpoints": "[]"})
    sender_2 = Relation("send-otlp", remote_app_data={"endpoints": "[]"})
    state = State(
        relations=[receiver, sender_1, sender_2],
        leader=True,
        containers=otelcol_container,
        model=Model("otelcol", uuid="f4d59020-c8e7-4053-8044-a2c1e5591c7f"),
    )

    # WHEN any event executes the reconciler
    state_out = ctx.run(ctx.on.update_status(), state=state)
    for relation in list(state_out.relations):
        if relation.endpoint != "send-otlp":
            continue
        assert (decompressed := _decompress(relation.local_app_data.get("rules")))
        databag = OtlpConsumerAppData.model_validate({"rules": decompressed, "metadata": metadata})
        assert isinstance(databag.rules, RulesModel)

        # --- logql assertions ---
        # THEN the upstream databag alert rule has topology labels injected
        group_name = "otelcol_f4d59020_charm_x_foo_alerts"
        assert (actual := _get_group_by_name(databag.rules.logql, group_name))
        assert _rules_have_labels(actual, expected_labels)

        # THEN the upstream databag record rule has topology labels injected
        group_name = "otelcol_f4d59020_charm_x_foobar_alerts"
        assert (actual := _get_group_by_name(databag.rules.logql, group_name))
        assert _rules_have_labels(actual, expected_labels)

        # --- promql assertions ---
        # THEN the upstream databag alert rule has topology labels injected
        group_name = "otelcol_f4d59020_charm_x_bar_alerts"
        assert (actual := _get_group_by_name(databag.rules.promql, group_name))
        assert _rules_have_labels(actual, expected_labels)

        # THEN the upstream databag record rule has topology labels injected
        group_name = "otelcol_f4d59020_charm_x_barfoo_alerts"
        assert (actual := _get_group_by_name(databag.rules.promql, group_name))
        assert _rules_have_labels(actual, expected_labels)

        # THEN the bundled alert rule has topology labels injected
        group_name = "otelcol_f4d59020_opentelemetry_collector_k8s_Hardware_alerts"
        assert (actual := _get_group_by_name(databag.rules.promql, group_name))
        assert _rules_have_labels(actual, OTELCOL_LABELS)

        # THEN the generic alert rule has topology labels injected
        group_name = "otelcol_f4d59020_opentelemetry_collector_k8s_AggregatorHostHealth_alerts"
        assert (actual := _get_group_by_name(databag.rules.promql, group_name))
        assert _rules_have_labels(actual, OTELCOL_LABELS)