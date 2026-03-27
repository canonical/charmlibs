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

"""Fixtures for unit tests, typically mocking out parts of the external system."""

from __future__ import annotations

import logging
import socket
from copy import deepcopy
from typing import Literal
from unittest.mock import patch

import ops
import pytest
from cosl.juju_topology import JujuTopology
from cosl.types import AlertingRuleFormat, OfficialRuleFileFormat, RecordingRuleFormat
from ops import testing
from ops.charm import CharmBase

from charmlibs.interfaces.otlp import OtlpProvider, OtlpRequirer, RuleStore
from helpers import patch_cos_tool_path

logger = logging.getLogger(__name__)

PEERS_ENDPOINT = 'my-peers'
LOKI_RULES_DEST_PATH = 'loki_alert_rules'
METRICS_RULES_DEST_PATH = 'prometheus_alert_rules'
SINGLE_LOGQL_ALERT = AlertingRuleFormat(
    alert='HighLogVolume',
    expr='count_over_time({job=~".+"}[30s]) > 100',
    labels={'severity': 'high'},
)
SINGLE_LOGQL_RECORD = RecordingRuleFormat(
    record='log:error_rate:rate5m',
    expr='sum by (service) (rate({job=~".+"} | json | level="error" [5m]))',
    labels={'severity': 'high'},
)
SINGLE_PROMQL_ALERT = AlertingRuleFormat(
    alert='Workload Missing',
    expr='up{job=~".+"} == 0',
    for_='0m',
    labels={'severity': 'critical'},
)
SINGLE_PROMQL_RECORD = RecordingRuleFormat(
    record='code:prometheus_http_requests_total:sum',
    expr='sum by (code) (prometheus_http_requests_total{job=~".+"})',
    labels={'severity': 'high'},
)
OFFICIAL_LOGQL_RULES = OfficialRuleFileFormat(
    groups=[
        {
            'name': 'test_logql',
            'rules': [SINGLE_LOGQL_ALERT, SINGLE_LOGQL_RECORD],
        },
    ]
)
OFFICIAL_PROMQL_RULES = OfficialRuleFileFormat(
    groups=[
        {
            'name': 'test_promql',
            'rules': [SINGLE_PROMQL_ALERT, SINGLE_PROMQL_RECORD],
        },
    ]
)
ALL_PROTOCOLS: list[Literal['grpc', 'http']] = ['grpc', 'http']
ALL_TELEMETRIES: list[Literal['logs', 'metrics', 'traces']] = ['logs', 'metrics', 'traces']


# --- Tester charms ---


class OtlpRequirerCharm(CharmBase):
    _aggregator_peer_relation_name: str | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.framework.observe(self.on.update_status, self._publish_rules)

    def _publish_rules(self, _: ops.EventBase) -> None:
        with patch_cos_tool_path():
            rules = (
                RuleStore(JujuTopology.from_charm(self))
                .add_logql(deepcopy(SINGLE_LOGQL_ALERT), group_name='test_logql_alert')
                .add_logql(deepcopy(SINGLE_LOGQL_RECORD), group_name='test_logql_record')
                .add_promql(deepcopy(SINGLE_PROMQL_ALERT), group_name='test_promql_alert')
                .add_promql(deepcopy(SINGLE_PROMQL_RECORD), group_name='test_promql_record')
                .add_logql(deepcopy(OFFICIAL_LOGQL_RULES))
                .add_promql(deepcopy(OFFICIAL_PROMQL_RULES))
            )
        OtlpRequirer(
            self,
            protocols=ALL_PROTOCOLS,
            telemetries=ALL_TELEMETRIES,
            aggregator_peer_relation_name=self._aggregator_peer_relation_name,
            rules=rules,
        ).publish()


class OtlpProviderCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.framework.observe(self.on.update_status, self._publish_endpoints)

    def _publish_endpoints(self, _: ops.EventBase) -> None:
        OtlpProvider(self).add_endpoint(
            protocol='http', endpoint=f'{socket.getfqdn()}:4318', telemetries=['metrics']
        ).publish()


# --- Fixtures ---


@pytest.fixture(autouse=True)
def mock_hostname():
    with patch('socket.getfqdn', return_value='http://fqdn'):
        yield


@pytest.fixture
def otlp_requirer_ctx(request: pytest.FixtureRequest) -> testing.Context[OtlpRequirerCharm]:
    meta = {
        'name': 'otlp-requirer',
        'requires': {'send-otlp': {'interface': 'otlp'}},
        'peers': {PEERS_ENDPOINT: {'interface': 'aggregator_peers'}},
    }
    # We want to be able to test generic aggregator rules injection and the application rules
    # injection case, which is toggled by an aggregator peer relation name input.
    generic_aggregator_rules: bool = getattr(request, 'param', False)
    charm_cls = type(
        'OtlpRequirerCharm',
        (OtlpRequirerCharm,),
        {'_aggregator_peer_relation_name': PEERS_ENDPOINT if generic_aggregator_rules else None},
    )
    return testing.Context(charm_cls, meta=meta)


@pytest.fixture
def otlp_provider_ctx() -> testing.Context[OtlpProviderCharm]:
    meta = {'name': 'otlp-provider', 'provides': {'receive-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpProviderCharm, meta=meta)
