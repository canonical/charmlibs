# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Charm the application."""

from __future__ import annotations

import logging
import socket

import ops

# TODO: switch to recommended form `from charmlibs import pathops`
#       after next pyright release fixes:
#       https://github.com/microsoft/pyright/issues/10203
import charmlibs.nginx as nginx

logger = logging.getLogger(__name__)

NGINX_CONTAINER = 'nginx'
NGINX_PROM_EXPORTER_CONTAINER = 'nginx-pexp'


class Charm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.nginx_container = self.unit.get_container(NGINX_CONTAINER)
        self.nginx_pexp_container = self.unit.get_container(NGINX_PROM_EXPORTER_CONTAINER)

        self.nginx_config = nginx.NginxConfig(
            server_name=socket.getfqdn(),
            upstream_configs=[],
            server_ports_to_locations={
                # forward traffic on port 8888 to /foo
                8888: [nginx.NginxLocationConfig('/', 'foo')]
            },
        )
        self.nginx = nginx.Nginx(container=self.nginx_container, nginx_config=self.nginx_config)
        self.nginx_pexp = nginx.NginxPrometheusExporter(container=self.nginx_pexp_container)

        for evt in (
            self.on[NGINX_CONTAINER].pebble_ready,
            self.on.start,
            self.on.install,
            self.on.update_status,
        ):
            framework.observe(evt, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self.on.inspect_action, self._on_inspect_action)

    def _reconcile(self, _event):
        self.nginx.reconcile(upstreams_to_addresses={}, tls_config=None)
        self.nginx_pexp.reconcile()

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent):
        event.add_status(ops.ActiveStatus())

    def _on_inspect_action(self, event: ops.ActionEvent):
        event.set_results({
            'nginx_config': self.nginx_container.pull(nginx.nginx.NGINX_CONFIG),
            'nginx_prom_exporter_plan': self.nginx_pexp_container.get_plan().to_yaml(),
        })


if __name__ == '__main__':  # pragma: nocover
    ops.main(Charm)
