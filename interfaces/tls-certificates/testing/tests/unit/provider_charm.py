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

Runs a small certificate authority of its own, so that a test can watch it answer the
requests a ``RemoteRequirer`` makes. Its CA is generated once at import, not per event, so
that repeated reconciles issue against a stable issuer.
"""

import datetime

import ops

from charmlibs.interfaces import tls_certificates

META = {
    "name": "provider",
    "provides": {"certificates": {"interface": "tls-certificates"}},
}
CAPABILITIES = tls_certificates.ProviderCapabilities(
    provider_type="charmlibs-test-ca", supports_ca_certificates=True
)
_VALIDITY = datetime.timedelta(days=365)
_CA_KEY = tls_certificates.PrivateKey.generate()
_CA_CERT = tls_certificates.Certificate.generate_self_signed_ca(
    attributes=tls_certificates.CertificateRequestAttributes(common_name="provider-charm-ca"),
    private_key=_CA_KEY,
    validity=datetime.timedelta(days=365 * 10),
)


class ProviderCharm(ops.CharmBase):
    """A minimal provider charm that signs every request it is given."""

    requests: list[tls_certificates.CertificateSigningRequest] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesProvidesV4(
            self, "certificates", provider_capabilities=CAPABILITIES
        )
        framework.observe(self.on.update_status, self._reconcile)
        framework.observe(self.on["certificates"].relation_changed, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        requests = self.certificates.get_certificate_requests()
        self.requests = [r.certificate_signing_request for r in requests] or None
        if not self.unit.is_leader():
            # Publishing is leader-only; the library warns and does nothing otherwise.
            self.unit.status = ops.ActiveStatus()
            return
        for request in self.certificates.get_outstanding_certificate_requests():
            certificate = request.certificate_signing_request.sign(
                ca=_CA_CERT,
                ca_private_key=_CA_KEY,
                validity=_VALIDITY,
                is_ca=request.is_ca,
            )
            self.certificates.set_relation_certificate(
                tls_certificates.ProviderCertificate(
                    relation_id=request.relation_id,
                    certificate=certificate,
                    certificate_signing_request=request.certificate_signing_request,
                    ca=_CA_CERT,
                    chain=[certificate, _CA_CERT],  # leaf to root
                )
            )
        self.unit.status = ops.ActiveStatus()
