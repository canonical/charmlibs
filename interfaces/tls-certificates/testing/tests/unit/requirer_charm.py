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

"""Example requirer charm for unit tests.

Lets the library generate and manage its private key -- the recommended configuration.
See requirer_charm_manual.py for a charm that manages its own key.
"""

import ops

from charmlibs.interfaces import tls_certificates

META = {
    "name": "requirer",
    "requires": {
        "certificates": {"interface": "tls-certificates"},
        # A second, unrelated endpoint, so that tests can check the rest of the state is
        # preserved. ops.testing rejects a relation whose endpoint isn't in the metadata.
        "other-endpoint": {"interface": "something-else"},
    },
}
REQUESTS = [
    tls_certificates.CertificateRequestAttributes(common_name="example.com"),
    tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
]


class RequirerCharm(ops.CharmBase):
    """A minimal requirer charm for testing the tls-certificates interface."""

    certs: list[tls_certificates.Certificate] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=REQUESTS,
        )
        framework.observe(self.on.update_status, self._reconcile)
        # The library emits certificate_available on every reconcile that finds a matching
        # certificate -- it is level-triggered, not a change signal -- so the handler must
        # reconcile against installed state rather than treat each event as news.
        framework.observe(self.certificates.on.certificate_available, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        certs, _private_key = self.certificates.get_assigned_certificates()
        if len(certs) != len(REQUESTS):
            self.certs = None
            self.unit.status = ops.BlockedStatus("TLS certificates not available")
            return
        self.certs = [c.certificate for c in certs]  # imagine we do something with these
        self.unit.status = ops.ActiveStatus("TLS ready")
