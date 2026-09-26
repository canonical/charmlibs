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

Transfers its own CA certificate to every relation on its endpoint, as a certificate
authority charm does, so that a test can watch it answer a ``RemoteRequirer``.
"""

from __future__ import annotations

import ops

from charmlibs.interfaces import certificate_transfer

META = {
    'name': 'provider',
    'provides': {'send-ca-cert': {'interface': 'certificate_transfer'}},
}
CA_CERT = '-----BEGIN CERTIFICATE-----\nthe provider charm under test\n-----END CERTIFICATE-----'
"""Deliberately not a certificate the simulated provider has, so tests can tell them apart.

The interface never parses what it transfers, so a charm's own CA can be any string here.
"""


class ProviderCharm(ops.CharmBase):
    """A minimal provider charm that transfers one CA certificate to everyone."""

    transferred: bool = False

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.ct = certificate_transfer.CertificateTransferProvides(self, 'send-ca-cert')
        framework.observe(self.on.update_status, self._reconcile)
        framework.observe(self.on['send-ca-cert'].relation_joined, self._reconcile)
        framework.observe(self.on['send-ca-cert'].relation_changed, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        if not self.unit.is_leader():
            # Transferring is leader-only; the library warns and does nothing otherwise.
            self.unit.status = ops.ActiveStatus()
            return
        self.ct.add_certificates({CA_CERT})
        self.transferred = True
        self.unit.status = ops.ActiveStatus('CA certificate transferred')
