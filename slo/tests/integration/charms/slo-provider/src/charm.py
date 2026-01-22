#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test charm that provides SLO specifications."""

import logging
from typing import Any

import ops

from charmlibs.slo.slo import SLOProvider

logger = logging.getLogger(__name__)


class SLOTestProviderCharm(ops.CharmBase):
    """Test charm that provides SLO specifications."""

    def __init__(self, framework: ops.Framework, *args: Any) -> None:
        super().__init__(framework, *args)

        self.slo_provider = SLOProvider(self, relation_name='slos')

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.slos_relation_joined, self._on_slos_relation_joined)
        self.framework.observe(self.on.slos_relation_changed, self._on_slos_relation_changed)

    def _on_install(self, event: ops.InstallEvent):
        """Handle install event."""
        self.unit.status = ops.ActiveStatus('Provider ready')

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Handle config changed event."""
        self._provide_slo()
        self.unit.status = ops.ActiveStatus('Config updated')

    def _on_slos_relation_joined(self, event: ops.RelationJoinedEvent):
        """Handle SLO relation joined."""
        self._provide_slo()

    def _on_slos_relation_changed(self, event: ops.RelationChangedEvent):
        """Handle SLO relation changed."""
        self._provide_slo()

    def _provide_slo(self):
        """Provide SLO specification."""
        service_name = str(self.config.get('slo-service-name', 'test-service'))
        objective = float(self.config.get('slo-objective', '99.9'))

        # Create a comprehensive SLO specification
        slo_spec = f"""
version: prometheus/v1
service: {service_name}
labels:
  team: test-team
  component: integration-test
slos:
  - name: requests-availability
    objective: {objective}
    description: "{objective}% of requests should succeed"
    sli:
      events:
        error_query: >-
          sum(rate(http_requests_total{{service="{service_name}",status=~"5.."}}[{{{{.window}}}}]))
        total_query: >-
          sum(rate(http_requests_total{{service="{service_name}"}}[{{{{.window}}}}]))
    alerting:
      name: {service_name.replace('-', '').title()}HighErrorRate
      labels:
        severity: critical
      annotations:
        summary: "{service_name} is experiencing high error rate"
"""

        try:
            self.slo_provider.provide_slos(slo_spec)
            logger.info(
                "Provided SLO for service '%s' with %s%% objective", service_name, objective
            )
        except Exception as e:
            logger.error('Failed to provide SLO: %s', e)
            self.unit.status = ops.BlockedStatus(f'Failed to provide SLO: {e}')


if __name__ == '__main__':
    ops.main(SLOTestProviderCharm)
