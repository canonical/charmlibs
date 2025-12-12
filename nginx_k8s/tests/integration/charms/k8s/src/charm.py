# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Charm the application."""

from __future__ import annotations

import logging
import socket
import time

import ops

# TODO: switch to recommended form `from charmlibs import pathops`
#       after next pyright release fixes:
#       https://github.com/microsoft/pyright/issues/10203
import charmlibs.nginx_k8s as nginx

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
        self.nginx = nginx.Nginx(container=self.nginx_container)
        self.nginx_pexp = nginx.NginxPrometheusExporter(container=self.nginx_pexp_container)

        for evt in (
            self.on[NGINX_CONTAINER].pebble_ready,
            self.on[NGINX_PROM_EXPORTER_CONTAINER].pebble_ready,
            self.on.start,
            self.on.install,
            self.on.update_status,
        ):
            framework.observe(evt, self._reconcile)
        framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        framework.observe(self.on.inspect_action, self._on_inspect_action)

    def _reconcile(self, _: ops.EventBase):
        if self.nginx_container.can_connect():
            self.nginx.reconcile(
                nginx_config=self.nginx_config.get_config(
                    upstreams_to_addresses={},
                    listen_tls=False,
                ),
                tls_config=None,
            )
        if self.nginx_pexp_container.can_connect():
            self.nginx_pexp.reconcile()

            # nginx-pexp can error out if started too quickly==before nginx is up
            nginx_pexp_pebble = self.nginx_pexp_container.pebble
            for _i in range(5):
                if nginx_pexp_pebble.get_services()[0].is_running():
                    return
                time.sleep(0.5)
                nginx_pexp_pebble.autostart_services()

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent):
        if not (self.nginx_container.can_connect() and self.nginx_pexp_container.can_connect()):
            event.add_status(ops.WaitingStatus('waiting for containers...'))
        else:
            if not self.nginx_pexp_container.pebble.get_services()[0].is_running():
                event.add_status(ops.BlockedStatus('nginx-pexp service down'))
            if not self.nginx_container.pebble.get_services()[0].is_running():
                event.add_status(ops.BlockedStatus('nginx service down'))
        event.add_status(ops.ActiveStatus())

    def _on_inspect_action(self, event: ops.ActionEvent):
        event.set_results({
            'nginx-up': self.nginx_container.get_service('nginx').is_running(),
            'nginx-pexp-up': self.nginx_pexp_container.get_service(
                'nginx-prometheus-exporter'
            ).is_running(),
            'nginx-config': self.nginx_container.pull(nginx.Nginx.NGINX_CONFIG).read(),
            'nginx-prom-exporter-plan': self.nginx_pexp_container.get_plan().to_yaml(),
        })


if __name__ == '__main__':  # pragma: nocover
    ops.main(Charm)
