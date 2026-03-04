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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import ops
import pytest
import yaml
from ops import testing
from ops.charm import CharmBase

from charmlibs.otlp import OtlpConsumer, OtlpProvider
from helpers import patch_cos_tool_path

logger = logging.getLogger(__name__)


@pytest.fixture
def ctx() -> testing.Context[ops.CharmBase]:
    return testing.Context(
        ops.CharmBase,
        meta={
            'name': 'tony',
            'containers': {'nginx': {}, 'nginx-pexp': {}},
        },
    )


@pytest.fixture(autouse=True)
def mock_hostname():
    with patch('socket.getfqdn', return_value='http://fqdn'):
        yield


# Minimal test charms used by unit tests
class OtlpConsumerCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        # instantiate the library object the tests rely on
        self.otlp_consumer = OtlpConsumer(
            self, protocols=['http', 'grpc'], telemetries=['metrics', 'logs']
        )
        # observe the library's endpoints_changed event if present (no-op handler)
        try:
            self.framework.observe(
                self.otlp_consumer.on.endpoints_changed, self._on_endpoints_changed
            )
        except Exception as e:
            # some library objects may not expose events in unit tests; ignore
            logger.info('An exception occurred when observing the event: %s', e)

        # observe update-status to trigger the consumer's publish in tests
        try:
            self.framework.observe(self.on.update_status, self._on_update_status)
        except Exception as e:
            logger.info('An exception occurred when observing the event: %s', e)

    def _on_endpoints_changed(self, event: ops.EventBase):
        return None

    def _on_update_status(self, event: ops.EventBase) -> None:
        # Trigger the library to (re)publish consumer data to related apps
        try:
            self.otlp_consumer.publish()
        except Exception:
            # In unit-tests the filesystem or relations may not exist as in real charms;
            # swallow errors
            return None


class OtlpProviderCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.otlp_provider = OtlpProvider(self)
        # observe update-status to add and publish provider endpoints in tests
        try:
            self.framework.observe(self.on.update_status, self._on_update_status)
        except Exception as e:
            logger.info('An exception occurred when observing the event: %s', e)

    def _on_update_status(self, event: ops.EventBase) -> None:
        # Add a default HTTP metrics endpoint and publish it
        try:
            self.otlp_provider.add_endpoint(
                protocol='http', endpoint=f'{socket.getfqdn()}:4318', telemetries=['metrics']
            )
            self.otlp_provider.publish()
        except Exception:
            return None


# Fixtures returning testing.Context for each charm type
@pytest.fixture
def otlp_consumer_ctx() -> testing.Context[OtlpConsumerCharm]:
    meta = {'name': 'otlp-consumer', 'requires': {'send-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpConsumerCharm, meta=meta)


@pytest.fixture
def otlp_provider_ctx() -> testing.Context[OtlpProviderCharm]:
    meta = {'name': 'otlp-provider', 'provides': {'receive-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpProviderCharm, meta=meta)


LOKI_RULES_DEST_PATH = 'loki_alert_rules'
METRICS_RULES_DEST_PATH = 'prometheus_alert_rules'

@patch_cos_tool_path
def _add_alerts(alerts: dict[str, dict[str, Any]], dest_path: Path) -> None:
    """Save the alerts to files in the specified destination folder.

    For K8s charms, alerts are saved in the charm container.

    Args:
        alerts: Dictionary of alerts to save to disk
        dest_path: Path to the folder where alerts will be saved
    """
    dest_path.mkdir(parents=True, exist_ok=True)
    for topology_identifier, rule in alerts.items():
        rule_file = dest_path.joinpath(f'juju_{topology_identifier}.rules')
        rule_file.write_text(yaml.safe_dump(rule))
        logger.debug('updated alert rules file: %s', rule_file.as_posix())


# Charm used in tests that acts as both an OTLP provider and consumer
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

        try:
            self.framework.observe(
                self.otlp_consumer.on.endpoints_changed, self._on_endpoints_changed
            )
        except Exception as e:
            logger.info('An exception occurred when observing the event: %s', e)

        # Observe update-status to publish both provider and consumer data
        try:
            self.framework.observe(self.on.update_status, self._on_update_status)
        except Exception as e:
            logger.info('An exception occurred when observing the event: %s', e)

    def _on_endpoints_changed(self, event: ops.EventBase) -> None:
        return None

    def _on_update_status(self, event: ops.EventBase) -> None:
        # add a provider endpoint and publish both sides
        forward_alert_rules = cast('bool', self.config.get('forward_alert_rules'))
        try:
            self.otlp_provider.add_endpoint(
                protocol='http', endpoint=f'{socket.getfqdn()}:4318', telemetries=['metrics']
            )
            _add_alerts(
                alerts=self.otlp_provider.rules('logql') if forward_alert_rules else {},
                dest_path=self.charm_root.joinpath(*LOKI_RULES_DEST_PATH.split('/')),
            )
            _add_alerts(
                alerts=self.otlp_provider.rules('promql') if forward_alert_rules else {},
                dest_path=self.charm_root.joinpath(*METRICS_RULES_DEST_PATH.split('/')),
            )
        except Exception:
            logger.error('An exception occurred when preparing the OTLP provider')
        try:
            self.otlp_provider.publish()
        except Exception:
            logger.error("An exception in the OTLP Provider's publish method")
        try:
            self.otlp_consumer.publish()
        except Exception:
            logger.error("An exception in the OTLP Consumer's publish method")


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
