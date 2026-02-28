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

"""Example provider charm for unit tests."""

import ops

from charmlibs.interfaces import tls_certificates

META = {
    "name": "provider",
    "provides": {"certificates": {"interface": "tls-certificates"}},
}


class ProviderCharm(ops.CharmBase):
    """A minimal provider charm for testing the TLS Certificates interface."""

    requests: list[tls_certificates.CertificateSigningRequest] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesProvidesV4(self, "certificates")
        framework.observe(self.on.update_status, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        requests = self.certificates.get_certificate_requests()
        if not requests:
            return
        # imagine we do something with the requests here, like sign them and provide certs back
        self.requests = [r.certificate_signing_request for r in requests]
