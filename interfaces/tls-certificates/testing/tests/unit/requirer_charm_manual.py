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

"""Example requirer charm that supplies its own private key.

The library's other key mode: the charm passes ``private_key``, so the library manages no key
secret of its own. Under the old fixture API this was the awkward case, because the fixture
signed its requests with a key the charm had to be made to use. It is no longer special:
the provider signs whatever the charm published, with whatever key it used.
"""

import ops

import _keys
from charmlibs.interfaces import tls_certificates

META = {
    "name": "requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
REQUESTS = [
    tls_certificates.CertificateRequestAttributes(common_name="example.com"),
    tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
]
# Generated for this test charm only. Stands in for a key the charm sources itself, for
# example from Juju config or a user-supplied secret.
PRIVATE_KEY = tls_certificates.PrivateKey.from_string(_keys.MANUAL_CHARM_KEY)


class ManualRequirerCharm(ops.CharmBase):
    """A minimal requirer charm that supplies its own private key."""

    certs: list[tls_certificates.Certificate] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=REQUESTS,
            private_key=PRIVATE_KEY,
        )
        framework.observe(self.on.update_status, self._reconcile)
        framework.observe(self.certificates.on.certificate_available, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        certs, _private_key = self.certificates.get_assigned_certificates()
        if len(certs) != len(REQUESTS):
            self.certs = None
            self.unit.status = ops.BlockedStatus("TLS certificates not available")
            return
        self.certs = [c.certificate for c in certs]
        self.unit.status = ops.ActiveStatus("TLS ready")
