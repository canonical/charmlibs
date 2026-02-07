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

"""Tests for the TLS Certificates testing library from a requirer charm perspective."""

import ops
import ops.testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing

META = {
    "name": "requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
REQUESTS = [
    tls_certificates.CertificateRequestAttributes(common_name="example.com"),
    tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
]


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
            private_key=tls_certificates_testing.DEFAULT_PRIVATE_KEY,
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


def test_requirer_no_relation():
    """Test requirer charm without any relation - should be blocked."""
    ctx = ops.testing.Context(RequirerCharm, meta=META)
    with ctx(ctx.on.update_status(), ops.testing.State()) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_requirer_relation_empty():
    """Test requirer charm when the relation is joined."""
    ctx = ops.testing.Context(RequirerCharm, meta=META)
    relation = ops.testing.Relation("certificates", interface="tls-certificates")
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_requirer_relation_has_certs():
    """Test requirer charm receiving certificates from a provider.

    Uses the testing library to populate the relation with provider certificates.
    """
    ctx = ops.testing.Context(RequirerCharm, meta=META)
    relation = tls_certificates_testing.for_local_requirer(
        endpoint="certificates", certificate_requests=REQUESTS
    )
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    assert manager.charm.certs is not None
    assert {c.common_name for c in manager.charm.certs} == {r.common_name for r in REQUESTS}
