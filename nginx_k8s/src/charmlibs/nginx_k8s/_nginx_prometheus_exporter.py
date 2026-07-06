# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Nginx-prometheus-exporter module."""

import hashlib

import ops
import yaml

from ._tls_config import TLSConfig

PROM_EXPORTER_DIR = '/etc/exporter'
PROM_EXPORTER_KEY_PATH = f'{PROM_EXPORTER_DIR}/certs/server.key'
PROM_EXPORTER_CERT_PATH = f'{PROM_EXPORTER_DIR}/certs/server.crt'
PROM_EXPORTER_WEB_CONFIG = f'{PROM_EXPORTER_DIR}/web-config.yaml'


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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
        nginx_tls_port: int = 443,
        nginx_prometheus_exporter_port: int = 9113,
        nginx_serves_tls: bool = False,
    ) -> None:
        self.port = nginx_prometheus_exporter_port
        self._container = container
        self._nginx_insecure = nginx_insecure
        self._nginx_port = nginx_port
        self._nginx_tls_port = nginx_tls_port
        self._nginx_serves_tls = nginx_serves_tls

    def reconcile(
        self,
        tls_config: TLSConfig | None = None,
        # The Coordinator sets nginx_serves_tls to Nginx's are_certificates_on_disk property.
        nginx_serves_tls: bool = False,
    ) -> None:
        """Configure pebble layer and restart if necessary."""
        if not self._container.can_connect():
            return

        cert_hash = self._configure_tls(tls_config)
        web_config_hash = sha256(self.web_config)

        self._container.push(
            PROM_EXPORTER_WEB_CONFIG,
            self.web_config,
            make_dirs=True,
        )

        self._container.add_layer(
            self._layer_name,
            self._layer(
                reload_sentinel=f'{cert_hash},{web_config_hash}',
                nginx_serves_tls=nginx_serves_tls,
            ),
            combine=True,
        )

        self._container.replan()

    def _configure_tls(self, tls_config: TLSConfig | None) -> str:
        """Write certificates to disk."""
        if not tls_config:
            if self._container.exists(PROM_EXPORTER_KEY_PATH):
                self._container.remove_path(PROM_EXPORTER_KEY_PATH)
            if self._container.exists(PROM_EXPORTER_CERT_PATH):
                self._container.remove_path(PROM_EXPORTER_CERT_PATH)

            return sha256('')

        self._container.push(
            PROM_EXPORTER_KEY_PATH,
            tls_config.private_key,
            make_dirs=True,
            permissions=0o600,
        )

        self._container.push(
            PROM_EXPORTER_CERT_PATH,
            tls_config.server_cert,
            make_dirs=True,
            permissions=0o600,
        )

        return sha256(
            tls_config.private_key + tls_config.server_cert,
        )

    @property
    def are_certificates_on_disk(self) -> bool:
        """Return True if the certificates files are on disk.

        This is used to determine whether the exporter should serve
        metrics over HTTP or HTTPS
        by checking whether the certificates are present on THIS container's FS.
        It has no effect on whether or not the exporter will attempt to
        scrape nginx over HTTP or HTTPS.
        That is determined by the `nginx_serves_tls` parameter passed to the reconciler.
        """
        return (
            self._container.can_connect()
            and self._container.exists(PROM_EXPORTER_KEY_PATH)
            and self._container.exists(PROM_EXPORTER_CERT_PATH)
        )

    @property
    def web_config(self) -> str:
        cfg: dict[str, object] = {}

        if self.are_certificates_on_disk:
            cfg['tls_server_config'] = {
                'cert_file': PROM_EXPORTER_CERT_PATH,
                'key_file': PROM_EXPORTER_KEY_PATH,
            }

        return yaml.safe_dump(cfg)

    def _layer(self, reload_sentinel: str, nginx_serves_tls: bool = False) -> ops.pebble.Layer:
        return ops.pebble.Layer({
            'summary': 'Nginx prometheus exporter layer',
            'description': 'Pebble config layer for nginx-prometheus-exporter',
            'services': {
                self._service_name: {
                    'override': 'replace',
                    'summary': 'Nginx prometheus exporter',
                    'command': self.command(nginx_serves_tls=nginx_serves_tls),
                    'startup': 'enabled',
                    'environment': {
                        '_reload': reload_sentinel,
                    },
                }
            },
        })

    def command(self, nginx_serves_tls: bool = False) -> str:
        nginx_scheme = 'https' if nginx_serves_tls else 'http'
        nginx_port = self._nginx_tls_port if nginx_serves_tls else self._nginx_port

        return (
            f'{self._executable_name} '
            f'--web.listen-address=:{self.port} '
            f'--nginx.scrape-uri={nginx_scheme}://127.0.0.1:{nginx_port}/status '
            f'--no-nginx.ssl-verify '
            f'--web.config.file={PROM_EXPORTER_WEB_CONFIG}'
        )
