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

"""Pebble log forwarding utilities for OTLP endpoints.

This module provides a helper class for building Pebble log-forwarding layers
that send workload stdout/stderr to OTLP-compatible endpoints using Pebble's
native ``opentelemetry`` log target type.
"""

from __future__ import annotations

import logging
from typing import Any

from cosl.juju_topology import JujuTopology
from ops.pebble import Layer

from ._otlp import OtlpEndpoint

logger = logging.getLogger(__name__)


class PebbleLogForwarder:
    """Build Pebble log-forwarding layers for OTLP endpoints.

    This class provides static helpers that translate OTLP endpoint information
    (as returned by :attr:`OtlpRequirer.endpoints`) into a :class:`ops.pebble.Layer`
    whose ``log-targets`` section uses Pebble's ``opentelemetry`` log target type.

    Only endpoints whose ``telemetries`` include ``"logs"`` are included.

    Example usage::

        from charmlibs.interfaces.otlp import OtlpRequirer, PebbleLogForwarder

        otlp_endpoints = OtlpRequirer(charm, ...).endpoints
        layer = PebbleLogForwarder.build_otlp_layer(otlp_endpoints)
        container.add_layer(
            f"{container.name}-log-forwarding", layer, combine=True
        )

    To include Juju topology labels (recommended for Canonical Observability
    Stack integration), pass a :class:`~cosl.juju_topology.JujuTopology`::

        from cosl.juju_topology import JujuTopology

        layer = PebbleLogForwarder.build_otlp_layer(
            otlp_endpoints,
            topology=JujuTopology.from_charm(self),
        )
    """

    @staticmethod
    def _build_log_target(
        endpoint: OtlpEndpoint,
        *,
        topology: JujuTopology | None = None,
        enable: bool = True,
    ) -> dict[str, Any]:
        """Build a single Pebble log target entry.

        Args:
            endpoint: The OTLP endpoint to forward logs to.
            topology: Optional Juju topology for labelling log entries.
            enable: If ``True`` the target forwards all services; if ``False``
                it disables forwarding (``services: ["-all"]``).

        Returns:
            A dict suitable for inclusion in a ``log-targets`` mapping.
        """
        services = ['all'] if enable else ['-all']
        target: dict[str, Any] = {
            'override': 'replace',
            'type': 'opentelemetry',
            'location': endpoint.endpoint,
            'services': services,
        }
        if enable and topology:
            target['labels'] = {
                'product': 'Juju',
                'charm': topology.charm_name,
                'juju_model': topology.model,
                'juju_model_uuid': topology.model_uuid,
                'juju_application': topology.application,
                'juju_unit': topology.unit,
            }
        return target

    @staticmethod
    def build_otlp_layer(
        otlp_endpoints: dict[int, OtlpEndpoint],
        *,
        topology: JujuTopology | None = None,
    ) -> Layer:
        """Build a :class:`~ops.pebble.Layer` for log forwarding to OTLP endpoints.

        For each endpoint whose ``telemetries`` include ``"logs"``, a Pebble
        ``log-target`` of ``type: opentelemetry`` is created. Endpoints that do
        not advertise ``"logs"`` are silently skipped.

        Args:
            otlp_endpoints: A mapping of relation ID to
                :class:`OtlpEndpoint`, as returned by
                :attr:`OtlpRequirer.endpoints`.
            topology: Optional :class:`~cosl.juju_topology.JujuTopology`
                used to inject topology labels into every log target.

        Returns:
            A Pebble :class:`~ops.pebble.Layer` with the ``log-targets``
            section populated.
        """
        log_targets: dict[str, Any] = {}
        for relation_id, endpoint in otlp_endpoints.items():
            if 'logs' not in endpoint.telemetries:
                continue
            target_name = f'otlp-{relation_id}'
            log_targets[target_name] = PebbleLogForwarder._build_log_target(
                endpoint, topology=topology
            )
        return Layer({'log-targets': log_targets})
