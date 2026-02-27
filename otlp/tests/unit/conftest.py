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

import ops
import pytest
from ops import testing
from ops.charm import CharmBase

from charmlibs.otlp import OtlpConsumer, OtlpProvider

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


# Minimal test charms used by unit tests
class OtlpConsumerCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        # instantiate the library object the tests rely on
        self.otlp_consumer = OtlpConsumer(self)
        # observe the library's endpoints_changed event if present (no-op handler)
        try:
            self.framework.observe(
                self.otlp_consumer.on.endpoints_changed, self._on_endpoints_changed
            )
        except Exception as e:
            # some library objects may not expose events in unit tests; ignore
            logger.info('An exception occured when observing the event: %s', e)

    def _on_endpoints_changed(self, event: ops.EventBase):
        return None


class OtlpProviderCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.otlp_provider = OtlpProvider(self)


# Fixtures returning testing.Context for each charm type
@pytest.fixture
def otlp_consumer_ctx() -> testing.Context[OtlpConsumerCharm]:
    meta = {'name': 'otlp-consumer', 'requires': {'send-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpConsumerCharm, meta=meta)


@pytest.fixture
def otlp_provider_ctx() -> testing.Context[OtlpProviderCharm]:
    meta = {'name': 'otlp-provider', 'provides': {'receive-otlp': {'interface': 'otlp'}}}
    return testing.Context(OtlpProviderCharm, meta=meta)


# Charm used in tests that acts as both an OTLP provider and consumer
class OtlpDualCharm(CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.otlp_consumer = OtlpConsumer(self)
        self.otlp_provider = OtlpProvider(self)

        try:
            self.framework.observe(
                self.otlp_consumer.on.endpoints_changed, self._on_endpoints_changed
            )
        except Exception as e:
            logger.info('An exception occured when observing the event: %s', e)

    def _on_endpoints_changed(self):
        return None


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

