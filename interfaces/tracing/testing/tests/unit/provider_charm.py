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

"""Example provider charm for unit tests.

Enables a receiver for each protocol requested across all its relations, as a real tracing
backend does, so that a test can watch it answer what a ``RemoteRequirer`` asks for.
"""

from __future__ import annotations

import typing

import ops

from charmlibs.interfaces import tracing

META = {
    'name': 'provider',
    'provides': {'tracing': {'interface': 'tracing'}},
}
HOST = 'provider-charm.example.com'
PORTS: dict[str, int] = {
    'jaeger_grpc': 24250,
    'jaeger_thrift_http': 24268,
    'otlp_grpc': 14317,
    'otlp_http': 14318,
    'zipkin': 19411,
}
"""Deliberately not the ports the simulated provider uses, so tests can tell them apart."""


class ProviderCharm(ops.CharmBase):
    """A minimal provider charm that serves every protocol it is asked for."""

    enabled: list[tracing.ReceiverProtocol] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.tracing = tracing.TracingEndpointProvider(self)
        framework.observe(self.on.update_status, self._reconcile)
        framework.observe(self.tracing.on.request, self._reconcile)
        framework.observe(self.tracing.on.broken, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        # requested_protocols is unannotated, and everything it can hold is a protocol.
        protocols = typing.cast(
            'set[tracing.ReceiverProtocol]', self.tracing.requested_protocols()
        )
        requested = sorted(protocols)
        self.enabled = requested or None
        if not self.unit.is_leader():
            # Publishing is leader-only; the library raises otherwise.
            self.unit.status = ops.ActiveStatus()
            return
        self.tracing.publish_receivers([
            (protocol, _url(protocol))
            for protocol in requested
            # Real backends support a fixed set; anything else is silently not enabled.
            if protocol in PORTS
        ])
        self.unit.status = ops.ActiveStatus(f'serving {requested}')


def _url(protocol: tracing.ReceiverProtocol) -> str:
    """The URL this charm serves a protocol on: no scheme for gRPC, per the interface."""
    transport = tracing.receiver_protocol_to_transport_protocol[protocol]
    if transport is tracing.TransportProtocolType.grpc:
        return f'{HOST}:{PORTS[protocol]}'
    return f'http://{HOST}:{PORTS[protocol]}'
