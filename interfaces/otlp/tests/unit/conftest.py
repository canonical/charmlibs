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
from typing import Final, Literal
from unittest.mock import patch

import ops
import pytest
from ops import testing
from ops.charm import CharmBase

from charmlibs.interfaces.otlp import OtlpProvider, OtlpRequirer
from charmlibs.interfaces.otlp._otlp import DEFAULT_REQUIRER_RELATION_NAME as SEND
from helpers import add_alerts, patch_cos_tool_path

logger = logging.getLogger(__name__)

LOKI_RULES_DEST_PATH = 'loki_alert_rules'
METRICS_RULES_DEST_PATH = 'prometheus_alert_rules'
SINGLE_LOGQL_ALERT: Final = {
    'alert': 'HighLogVolume',
    'expr': 'count_over_time({job=~".+"}[30s]) > 100',
    'labels': {'severity': 'high'},
}
SINGLE_LOGQL_RECORD: Final = {
    'record': 'log:error_rate:rate5m',
    'expr': 'sum by (service) (rate({job=~".+"} | json | level="error" [5m]))',
    'labels': {'severity': 'high'},
}
SINGLE_PROMQL_ALERT: Final = {
    'alert': 'Workload Missing',
    'expr': 'up{job=~".+"} == 0',
    'for': '0m',
    'labels': {'severity': 'critical'},
}
SINGLE_PROMQL_RECORD: Final = {
    'record': 'code:prometheus_http_requests_total:sum',
    'expr': 'sum by (code) (prometheus_http_requests_total{job=~".+"})',
    'labels': {'severity': 'high'},
}
OFFICIAL_LOGQL_RULES: Final = {
    'groups': [
        {
            'name': 'test_logql',
            'rules': [SINGLE_LOGQL_ALERT, SINGLE_LOGQL_RECORD],
        },
    ]
}
OFFICIAL_PROMQL_RULES: Final = {
    'groups': [
        {
            'name': 'test_promql',
            'rules': [SINGLE_PROMQL_ALERT, SINGLE_PROMQL_RECORD],
        },
    ]
}
ALL_PROTOCOLS: Final[list[Literal['grpc', 'http']]] = ['grpc', 'http']
ALL_TELEMETRIES: Final[list[Literal['logs', 'metrics', 'traces']]] = ['logs', 'metrics', 'traces']


# --- Tester charms ---


class OtlpRequirerCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.charm_root = self.charm_dir.absolute()
        self.loki_rules_path = self.charm_root.joinpath(*LOKI_RULES_DEST_PATH.split('/'))
        self.prometheus_rules_path = self.charm_root.joinpath(*METRICS_RULES_DEST_PATH.split('/'))
        self.framework.observe(self.on.update_status, self._publish_rules)

    def _add_rules_to_disk(self):
        with patch_cos_tool_path():
            add_alerts(
                alerts={'test_identifier': OFFICIAL_LOGQL_RULES}, dest_path=self.loki_rules_path
            )
            add_alerts(
                alerts={'test_identifier': OFFICIAL_PROMQL_RULES},
                dest_path=self.prometheus_rules_path,
            )

    def _publish_rules(self, _: ops.EventBase) -> None:
        self._add_rules_to_disk()
        OtlpRequirer(
            self,
            SEND,
            ALL_PROTOCOLS,
            ALL_TELEMETRIES,
            loki_rules_path=self.loki_rules_path,
            prometheus_rules_path=self.prometheus_rules_path,
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
def otlp_requirer_ctx() -> testing.Context[OtlpRequirerCharm]:
    meta = {'name': 'otlp-requirer', 'requires': {'send-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpRequirerCharm, meta=meta)


@pytest.fixture
def otlp_provider_ctx() -> testing.Context[OtlpProviderCharm]:
    meta = {'name': 'otlp-provider', 'provides': {'receive-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpProviderCharm, meta=meta)
