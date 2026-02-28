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
import pytest

import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing
import requirer_charm


def test_requirer_no_relation():
    """Test requirer charm without any relation - should be blocked."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    with ctx(ctx.on.update_status(), ops.testing.State()) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_requirer_relation_empty():
    """Test requirer charm when the relation is joined."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = ops.testing.Relation("certificates", interface="tls-certificates")
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_requirer_relation_has_certs(monkeypatch: pytest.MonkeyPatch):
    """Test requirer charm receiving certificates from a provider.

    Uses the testing library to populate the relation with provider certificates.
    Patches the charm module to make the private key used by the libraries match.
    """
    monkeypatch.setattr(
        requirer_charm, "PRIVATE_KEY", tls_certificates_testing.DEFAULT_PRIVATE_KEY
    )
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates", certificate_requests=requirer_charm.REQUESTS
    )
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    assert manager.charm.certs is not None
    assert {c.common_name for c in manager.charm.certs} == {
        r.common_name for r in requirer_charm.REQUESTS
    }
