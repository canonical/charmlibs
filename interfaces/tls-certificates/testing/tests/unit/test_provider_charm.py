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

"""Tests for the TLS Certificates testing library from a provider charm perspective."""

import ops
import ops.testing

# we skip sorting these imports because ruff wants to use:
# from charmlibs.interfaces import tls_certificates, tls_certificates_testing
# but this breaks pyright's ability to find the second and subsequent namespace package
from charmlibs.interfaces import tls_certificates  # isort: skip
from charmlibs.interfaces import tls_certificates_testing

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


def test_provider_no_relation():
    """Test provider charm without any relation - should be ready."""
    ctx = ops.testing.Context(ProviderCharm, meta=META)
    with ctx(ctx.on.update_status(), ops.testing.State()) as manager:
        manager.run()
    assert manager.charm.requests is None


def test_provider_relation_empty():
    """Test provider charm when the relation is empty - should be ready."""
    ctx = ops.testing.Context(ProviderCharm, meta=META)
    relation = ops.testing.Relation("certificates", interface="tls-certificates")
    state = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
    assert manager.charm.requests is None


def test_provider_relation_has_request():
    """Test provider charm receiving a certificate request from a requirer.

    Uses the testing library to populate the relation with a certificate request.
    """
    ctx = ops.testing.Context(ProviderCharm, meta=META)
    requests = [
        tls_certificates.CertificateRequestAttributes(common_name="example.com"),
        tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
    ]
    relation = tls_certificates_testing.for_local_provider(
        endpoint="certificates", certificate_requests=requests
    )
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        manager.run()
    assert manager.charm.requests is not None
    assert {r.common_name for r in manager.charm.requests} == {r.common_name for r in requests}
