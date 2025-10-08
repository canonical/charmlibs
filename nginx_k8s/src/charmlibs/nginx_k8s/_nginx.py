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

import ops
from ops import pebble

from ._config import NginxConfig
from ._tls_config import TLSConfig, TLSConfigManager
from ._tracer import tracer as _tracer

logger = logging.getLogger(__name__)


class Nginx:
    """Helper class to manage the nginx workload."""

    NGINX_CONFIG = '/etc/nginx/nginx.conf'

    _layer_name = 'nginx'
    _executable_name = 'nginx'
    _service_name = 'nginx'

    def __init__(
        self,
        container: ops.Container,
        nginx_config: NginxConfig,
        update_ca_certificates_on_restart: bool = True,
    ):
        self._nginx_config = nginx_config
        self._container = container
        self._tls_config_mgr = TLSConfigManager(container, update_ca_certificates_on_restart)

    def reconcile(
        self,
        upstreams_to_addresses: dict[str, set[str]],
        tls_config: TLSConfig | None = None,
    ):
        """Configure pebble layer and restart if necessary."""
        self._tls_config_mgr.reconcile(tls_config)
        self._reconcile_nginx_config(upstreams_to_addresses=upstreams_to_addresses)

    def _reconcile_nginx_config(self, upstreams_to_addresses: dict[str, set[str]]):
        if not self._container.can_connect():
            logger.debug('cannot connect to container; skipping nginx config reconcile')
            return

        new_config = self._nginx_config.get_config(
            upstreams_to_addresses=upstreams_to_addresses,
            listen_tls=self._tls_config_mgr.is_tls_enabled,
        )
        should_restart = self._has_config_changed(new_config)

        with _tracer.start_as_current_span('write config'):
            self._container.push(self.NGINX_CONFIG, new_config, make_dirs=True)

        self._container.add_layer(self._layer_name, self._layer, combine=True)
        self._container.autostart()

        if should_restart:
            logger.info('new nginx config: restarting the service')
            # Reload the nginx config without restarting the service
            self._container.exec([self._executable_name, '-s', 'reload']).wait()

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
    def _layer(self) -> pebble.Layer:
        """Return the Pebble layer for Nginx."""
        return pebble.Layer({
            'summary': 'Nginx service layer.',
            'description': 'Pebble config layer for Nginx',
            'services': {
                self._service_name: {
                    'override': 'replace',
                    'summary': 'Nginx service.',
                    'command': f"{self._executable_name} -g 'daemon off;'",
                    'startup': 'enabled',
                }
            },
        })
