# Copyright 2025 Canonical
# See LICENSE file for licensing details.

r"""Nginx module.

This module provides a set of abstractions for managing Nginx workloads.

- `Nginx`: A helper class for managing a Nginx sidecar container.

The Nginx class has a minimal public API consisting of a `reconcile` method that, when called,
generates the nginx config file, compares with the one on disk (if present), diffs it and restarts
the nginx server if necessary.

All container filesystem operations are performed through pebble.

It also manages the TLS configuration on disk.
"""

import logging
from collections.abc import Callable
from pathlib import Path

import ops
from ops import pebble

from ._config import NginxConfig
from ._tls_config import TLSConfig, TLSConfigManager
from ._tracer import tracer as _tracer

logger = logging.getLogger(__name__)


class Nginx:
    """Helper class to manage the nginx workload."""

    NGINX_DIR = '/etc/nginx'
    NGINX_CONFIG = f'{NGINX_DIR}/nginx.conf'
    KEY_PATH = f'{NGINX_DIR}/certs/server.key'
    CERT_PATH = f'{NGINX_DIR}/certs/server.cert'
    CA_CERT_PATH = '/usr/local/share/ca-certificates/ca.crt'

    _layer_name = 'nginx'
    _executable_name = 'nginx'
    _service_name = 'nginx'
    _liveness_check_name = 'nginx-up'

    def __init__(
        self,
        container: ops.Container,
        update_ca_certificates_on_restart: bool = True,
        liveness_check_endpoint_getter: Callable[[bool], str] | None = None,
    ):
        self._container = container
        self._liveness_check_endpoint_getter = liveness_check_endpoint_getter
        self._tls_config_mgr = TLSConfigManager(container, update_ca_certificates_on_restart)

    def reconcile(
        self,
        nginx_config: str,
        tls_config: TLSConfig | None = None,
    ):
        """Configure pebble layer and restart if necessary."""
        if self._container.can_connect():
            self._reconcile_tls_config(tls_config)
            self._reconcile_nginx_config(nginx_config)

    def _reconcile_tls_config(self, tls_config: TLSConfig | None = None):
        if tls_config:
            self._configure_tls(
                server_cert=tls_config.server_cert,
                ca_cert=tls_config.ca_cert,
                private_key=tls_config.private_key,
            )
        else:
            self._delete_certificates()

    @property
    def are_certificates_on_disk(self) -> bool:
        """Return True if the certificates files are on disk."""
        return (
            self._container.can_connect()
            and self._container.exists(self.CERT_PATH)
            and self._container.exists(self.KEY_PATH)
            and self._container.exists(self.CA_CERT_PATH)
        )

    def _configure_tls(self, private_key: str, server_cert: str, ca_cert: str) -> None:
        """Save the certificates file to disk and run update-ca-certificates."""
        with _tracer.start_as_current_span('write ca cert'):
            # push CA cert to charm container
            Path(self.CA_CERT_PATH).parent.mkdir(parents=True, exist_ok=True)
            Path(self.CA_CERT_PATH).write_text(ca_cert)

        if self._container.can_connect():
            # Read the current content of the files (if they exist)
            current_server_cert = (
                self._container.pull(self.CERT_PATH).read()
                if self._container.exists(self.CERT_PATH)
                else ''
            )
            current_private_key = (
                self._container.pull(self.KEY_PATH).read()
                if self._container.exists(self.KEY_PATH)
                else ''
            )
            current_ca_cert = (
                self._container.pull(self.CA_CERT_PATH).read()
                if self._container.exists(self.CA_CERT_PATH)
                else ''
            )

            if (
                current_server_cert == server_cert
                and current_private_key == private_key
                and current_ca_cert == ca_cert
            ):
                # No update needed
                return
            self._container.push(self.KEY_PATH, private_key, make_dirs=True)
            self._container.push(self.CERT_PATH, server_cert, make_dirs=True)
            self._container.push(self.CA_CERT_PATH, ca_cert, make_dirs=True)
            logger.debug('running update-ca-certificates')
            self._container.exec(['update-ca-certificates', '--fresh']).wait()

    def _delete_certificates(self) -> None:
        """Delete the certificate files from disk and run update-ca-certificates."""
        with _tracer.start_as_current_span('delete ca cert'):
            if Path(self.CA_CERT_PATH).exists():
                Path(self.CA_CERT_PATH).unlink(missing_ok=True)

        if self._container.can_connect():
            for path in (self.CERT_PATH, self.KEY_PATH, self.CA_CERT_PATH):
                if self._container.exists(path):
                    self._container.remove_path(path, recursive=True)
            logger.debug('running update-ca-certificates')
            self._container.exec(['update-ca-certificates', '--fresh']).wait()

    def _reconcile_nginx_config(self, nginx_config: str):
        should_restart = self._has_config_changed(nginx_config)
        self._container.push(self.NGINX_CONFIG, nginx_config, make_dirs=True)
        self._container.add_layer('nginx', self._pebble_layer(), combine=True)
        try:
            self._container.autostart()
        except pebble.ChangeError:
            # check if we're trying to load an external nginx module,
            # but it doesn't exist in the nginx image
            if 'ngx_otel_module' in nginx_config and not self._container.exists(
                NginxConfig.otel_module_path
            ):
                logger.exception(
                    'Failed to enable tracing for nginx. The nginx image is '
                    'missing the ngx_otel_module.'
                )
            # otherwise, it's an unexpected error and we should raise it as is
            raise
        if should_restart:
            logger.info('new nginx config: restarting the service')
            # Reload the nginx config without restarting the service
            self._container.exec(['nginx', '-s', 'reload']).wait()

    def _has_config_changed(self, new_config: str) -> bool:
        """Return True if the passed config differs from the one on disk."""
        if not self._container.can_connect():
            logger.debug('Could not connect to Nginx container')
            return False

        try:
            with _tracer.start_as_current_span('read config'):
                current_config = self._container.pull(self.NGINX_CONFIG).read()
        except pebble.PathError:
            logger.debug('nginx configuration file not found at %s', str(self.NGINX_CONFIG))
            # file does not exist! it's probably because it's the first time we're generating it.
            return True
        except pebble.ProtocolError as e:
            logger.warning(
                'Could not check the current nginx configuration due to '
                'a failure in retrieving the file: %s',
                e,
            )
            return False

        return current_config != new_config

    @property
    def _service_dict(self) -> pebble.ServiceDict:
        service_dict: pebble.ServiceDict = {
            'override': 'replace',
            'summary': 'nginx',
            'command': f"{self._executable_name} -g 'daemon off;'",
            'startup': 'enabled',
        }
        if self._liveness_check_endpoint_getter:
            # we've observed that nginx sometimes doesn't get reloaded after a config change.
            # Probably a race condition if we change the config too quickly, while the workers are
            # already reloading because of a previous config change.
            # To counteract this, we rely on the pebble health check: if this check fails,
            # pebble will automatically restart the nginx service.
            service_dict['on-check-failure'] = {self._liveness_check_name: 'restart'}
        return service_dict

    @property
    def _check_dict(self) -> pebble.CheckDict:
        if not self._liveness_check_endpoint_getter:
            return {}

        return {
            'override': 'replace',
            'startup': 'enabled',
            'threshold': 3,
            'http': {'url': self._liveness_check_endpoint_getter(self.are_certificates_on_disk)},
        }

    def _pebble_layer(self) -> pebble.Layer:
        """Return the Pebble layer for Nginx."""
        return pebble.Layer({
            'summary': 'Nginx layer.',
            'description': 'Pebble config layer for Nginx.',
            'services': {self._service_name: self._service_dict},
            'checks': {self._liveness_check_name: self._check_dict}
            if self._liveness_check_endpoint_getter
            else {},
        })
