# Copyright 2025 Canonical Ltd.
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

"""Example requirer charm for unit tests."""

import ops

import charmlibs.interfaces.tls_certificates as tls_certificates

META = {
    "name": "requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
REQUESTS = [
    tls_certificates.CertificateRequestAttributes(common_name="example.com"),
    tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
]
PRIVATE_KEY: tls_certificates.PrivateKey | None = None


class RequirerCharm(ops.CharmBase):
    """A minimal requirer charm for testing the TLS Certificates interface."""

    certs: list[tls_certificates.Certificate] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        # Define certificate requests
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=REQUESTS,
            private_key=PRIVATE_KEY,
        )
        framework.observe(self.on.update_status, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        """Handle relation changed event with certificates."""
        # Check if we got certificates and update status
        certs, _private_key = self.certificates.get_assigned_certificates()
        if not certs:
            self.unit.status = ops.BlockedStatus("TLS certificates not available")
            return
        self.certs = [c.certificate for c in certs]  # imagine we do something with the certs here
        self.unit.status = ops.ActiveStatus("TLS ready")
