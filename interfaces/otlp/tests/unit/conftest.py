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
from typing import cast
from unittest.mock import patch

import ops
import pytest
from ops import testing
from ops.charm import CharmBase

from charmlibs.otlp import OtlpConsumer, OtlpProvider
from helpers import add_alerts

logger = logging.getLogger(__name__)

LOKI_RULES_DEST_PATH = 'loki_alert_rules'
METRICS_RULES_DEST_PATH = 'prometheus_alert_rules'

# --- Tester charms ---


class OtlpConsumerCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.otlp_consumer = OtlpConsumer(
            self, protocols=['http', 'grpc'], telemetries=['metrics', 'logs']
        )
        self.framework.observe(self.on.update_status, self._on_update_status)

    def _on_update_status(self, event: ops.EventBase) -> None:
        self.otlp_consumer.publish()


class OtlpProviderCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.otlp_provider = OtlpProvider(self)
        self.framework.observe(self.on.update_status, self._on_update_status)

    def _on_update_status(self, event: ops.EventBase) -> None:
        self.otlp_provider.add_endpoint(
            protocol='http', endpoint=f'{socket.getfqdn()}:4318', telemetries=['metrics']
        )
        self.otlp_provider.publish()


class OtlpDualCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.charm_root = self.charm_dir.absolute()
        self.otlp_consumer = OtlpConsumer(
            self,
            protocols=['http', 'grpc'],
            telemetries=['metrics', 'logs'],
            loki_rules_path=self.charm_root.joinpath(*LOKI_RULES_DEST_PATH.split('/')),
            prometheus_rules_path=self.charm_root.joinpath(*METRICS_RULES_DEST_PATH.split('/')),
        )
        self.otlp_provider = OtlpProvider(self)
        self.framework.observe(self.on.update_status, self._on_update_status)

    def _on_update_status(self, event: ops.EventBase) -> None:
        forward_alert_rules = cast('bool', self.config.get('forward_alert_rules'))
        try:
            self.otlp_provider.add_endpoint(
                protocol='http', endpoint=f'{socket.getfqdn()}:4318', telemetries=['metrics']
            )
            add_alerts(
                alerts=self.otlp_provider.rules('logql') if forward_alert_rules else {},
                dest_path=self.charm_root.joinpath(*LOKI_RULES_DEST_PATH.split('/')),
            )
            add_alerts(
                alerts=self.otlp_provider.rules('promql') if forward_alert_rules else {},
                dest_path=self.charm_root.joinpath(*METRICS_RULES_DEST_PATH.split('/')),
            )
        except Exception:
            logger.error('An exception occurred when preparing the OTLP provider')

        self.otlp_provider.publish()
        self.otlp_consumer.publish()


# --- Fixtures ---


@pytest.fixture(autouse=True)
def mock_hostname():
    with patch('socket.getfqdn', return_value='http://fqdn'):
        yield


@pytest.fixture
def otlp_consumer_ctx() -> testing.Context[OtlpConsumerCharm]:
    meta = {'name': 'otlp-consumer', 'requires': {'send-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpConsumerCharm, meta=meta)


@pytest.fixture
def otlp_provider_ctx() -> testing.Context[OtlpProviderCharm]:
    meta = {'name': 'otlp-provider', 'provides': {'receive-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpProviderCharm, meta=meta)


@pytest.fixture
def otlp_dual_ctx() -> testing.Context[OtlpDualCharm]:
    meta = {
        'name': 'otlp-dual',
        'requires': {'send-otlp': {'interface': 'otlp'}},
        'provides': {'receive-otlp': {'interface': 'otlp'}},
    }
    config = {
        'options': {
            'forward_alert_rules': {
                'type': 'boolean',
                'default': True,
            },
        },
    }
    return testing.Context(OtlpDualCharm, meta=meta, config=config)
