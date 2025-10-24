# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Nginx-prometheus-exporter module."""

import ops


class NginxPrometheusExporter:
    """Helper class to manage the nginx prometheus exporter workload."""

    _service_name = 'nginx-prometheus-exporter'
    _layer_name = 'nginx-prometheus-exporter'
    _executable_name = 'nginx-prometheus-exporter'

    def __init__(
        self,
        container: ops.Container,
        nginx_port: int = 8080,
        nginx_insecure: bool = False,
        nginx_prometheus_exporter_port: int = 9113,
    ) -> None:
        self.port = nginx_prometheus_exporter_port
        self._container = container
        self._nginx_insecure = nginx_insecure
        self._nginx_port = nginx_port

    def reconcile(self):
        """Configure pebble layer and restart if necessary."""
        if self._container.can_connect():
            self._container.add_layer(self._layer_name, self.layer, combine=True)
            self._container.autostart()

    @property
    def layer(self) -> ops.pebble.Layer:
        """Return the Pebble layer for Nginx Prometheus exporter."""
        scheme = 'http' if self._nginx_insecure else 'https'
        return ops.pebble.Layer({
            'summary': 'Nginx prometheus exporter layer.',
            'description': 'Pebble config layer for the Nginx Prometheus exporter service.',
            'services': {
                self._service_name: {
                    'override': 'replace',
                    'summary': 'Nginx prometheus exporter service.',
                    'command': (
                        self._executable_name + ' '
                        # needed because nginx might have a cert, but it may be invalid
                        #  for 127.0.0.1
                        f'--no-nginx.ssl-verify '
                        f'--web.listen-address=:{self.port} '
                        f'--nginx.scrape-uri={scheme}://127.0.0.1:{self._nginx_port}/status'
                    ),
                    'startup': 'enabled',
                }
            },
        })
