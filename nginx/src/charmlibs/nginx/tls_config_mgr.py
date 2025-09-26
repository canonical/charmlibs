# Copyright 2025 Canonical
# See LICENSE file for licensing details.
"""TLSConfigManager.

Class that manages the TLS configuration for a sidecar container.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from pathlib import Path

from ._tracer import tracer as _tracer

if typing.TYPE_CHECKING:
    import ops

KEY_PATH = '/etc/nginx/certs/server.key'
CERT_PATH = '/etc/nginx/certs/server.cert'
CA_CERT_PATH = '/usr/local/share/ca-certificates/ca.cert'


@dataclass
class TLSConfig:
    """TLS configuration."""

    server_cert: str
    ca_cert: str
    private_key: str


class TLSConfigManager:
    """TLSConfigManager."""

    def __init__(
        self,
        container: ops.Container,
        update_ca_certificates_on_restart: bool = True,
    ):
        self._container = container
        self._update_ca_certificates_on_restart = update_ca_certificates_on_restart

    def reconcile(self, tls_config: TLSConfig | None):
        """Reconcile container state."""
        if tls_config:
            self._sync_certificates(tls_config)
        else:
            self._delete_certificates()

    @property
    def is_tls_enabled(self) -> bool:
        """Return True if the certificates files are on disk."""
        with _tracer.start_as_current_span('check tls config files exist'):
            return (
                self._container.can_connect()
                and self._container.exists(CERT_PATH)
                and self._container.exists(KEY_PATH)
                and self._container.exists(CA_CERT_PATH)
            )

    def _sync_certificates(self, tls_config: TLSConfig) -> None:
        """Save the certificates file to disk and run update-ca-certificates."""
        if self._container.can_connect():
            # Read the current content of the files (if they exist)
            with _tracer.start_as_current_span('read tls config files'):
                current_server_cert = (
                    self._container.pull(CERT_PATH).read()
                    if self._container.exists(CERT_PATH)
                    else ''
                )
                current_private_key = (
                    self._container.pull(KEY_PATH).read()
                    if self._container.exists(KEY_PATH)
                    else ''
                )
                current_ca_cert = (
                    self._container.pull(CA_CERT_PATH).read()
                    if self._container.exists(CA_CERT_PATH)
                    else ''
                )

            if (
                current_server_cert == tls_config.server_cert
                and current_private_key == tls_config.private_key
                and current_ca_cert == tls_config.ca_cert
            ):
                # No update needed
                return

            with _tracer.start_as_current_span('write tls config files'):
                self._container.push(KEY_PATH, tls_config.private_key, make_dirs=True)
                self._container.push(CERT_PATH, tls_config.server_cert, make_dirs=True)
                self._container.push(CA_CERT_PATH, tls_config.ca_cert, make_dirs=True)

            if self._update_ca_certificates_on_restart:
                self._container.exec(['update-ca-certificates', '--fresh'])

    def _delete_certificates(self) -> None:
        """Delete the certificate files from disk and run update-ca-certificates."""
        with _tracer.start_as_current_span('delete tls config files'):
            if Path(CA_CERT_PATH).exists():
                Path(CA_CERT_PATH).unlink(missing_ok=True)

            if self._container.can_connect():
                for path in (CERT_PATH, KEY_PATH, CA_CERT_PATH):
                    if self._container.exists(path):
                        self._container.remove_path(path, recursive=True)

        if self._container.can_connect() and self._update_ca_certificates_on_restart:
            self._container.exec(['update-ca-certificates', '--fresh'])
