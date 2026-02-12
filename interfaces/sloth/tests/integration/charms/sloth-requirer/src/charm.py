#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test charm that requires SLO specifications."""

import logging
from typing import Any

import ops

from charmlibs.interfaces.sloth import SlothRequirer

logger = logging.getLogger(__name__)


class SLOTestRequirerCharm(ops.CharmBase):
    """Test charm that consumes SLO specifications."""

    def __init__(self, framework: ops.Framework, *args: Any) -> None:
        super().__init__(framework, *args)

        self.sloth_requirer = SlothRequirer(self, relation_name='sloth')

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.sloth_relation_joined, self._on_sloth_relation_joined)
        self.framework.observe(self.on.sloth_relation_changed, self._on_sloth_relation_changed)
        self.framework.observe(self.on.get_slos_action, self._on_get_slos_action)

    def _on_install(self, event: ops.InstallEvent):
        """Handle install event."""
        self.unit.status = ops.ActiveStatus('Requirer ready')

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Handle config changed event."""
        self._update_status()

    def _on_sloth_relation_joined(self, event: ops.RelationJoinedEvent):
        """Handle SLO relation joined."""
        logger.info('SLO relation joined')
        self._update_status()

    def _on_sloth_relation_changed(self, event: ops.RelationChangedEvent):
        """Handle SLO relation changed."""
        logger.info('SLO relation changed')
        self._update_status()

    def _on_get_slos_action(self, event: ops.ActionEvent):
        """Action to retrieve all SLOs."""
        try:
            slos = self.sloth_requirer.get_slos()
            event.set_results({
                'count': len(slos),
                'services': ', '.join(slo.get('service', 'unknown') for slo in slos),
                'slos': str(slos),
            })
        except Exception as e:
            event.fail(f'Failed to get SLOs: {e}')

    def _update_status(self):
        """Update charm status based on received SLOs."""
        try:
            slos = self.sloth_requirer.get_slos()
            if slos:
                services = [slo.get('service', 'unknown') for slo in slos]
                service_list = ', '.join(services)
                self.unit.status = ops.ActiveStatus(
                    f'Received {len(slos)} SLO(s) from {service_list}'
                )
            else:
                self.unit.status = ops.ActiveStatus('No SLOs received yet')
        except Exception as e:
            logger.error('Failed to get SLOs: %s', e)
            self.unit.status = ops.BlockedStatus(f'Error: {e}')


if __name__ == '__main__':
    ops.main(SLOTestRequirerCharm)
