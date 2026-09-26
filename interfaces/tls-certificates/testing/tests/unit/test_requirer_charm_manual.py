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

"""Tests for a requirer charm that supplies its own private key.

The library's other key mode. It used to be the awkward one: the fixture signed its requests
with a key of its own, so the charm had to be made to use that key, through whatever seam it
happened to have. Deriving the answer from what the charm published removes the problem
entirely -- these tests are the same as the library-managed ones, with no extra arrangement.
"""

from __future__ import annotations

import typing

import ops
import ops.testing
import pytest

import requirer_charm_manual
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

CERTS = tls_certificates_testing.RemoteProvider("certificates")
REQUESTED = {r.common_name for r in requirer_charm_manual.REQUESTS}

_Ctx: typing.TypeAlias = "ops.testing.Context[requirer_charm_manual.ManualRequirerCharm]"


@pytest.fixture()
def ctx() -> _Ctx:
    return ops.testing.Context(
        requirer_charm_manual.ManualRequirerCharm, meta=requirer_charm_manual.META
    )


def test_the_happy_path_needs_no_extra_arrangement(ctx: _Ctx, mocked: None):
    """Identical to the library-managed case, which is the point."""
    state_out = CERTS.integrate(ctx, ops.testing.State.from_context(ctx))
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_the_charms_own_key_is_used(ctx: _Ctx, mocked: None):
    """The certificates are bound to the charm's key, not to one the package chose.

    The charm's key is deliberately not the key `mocked()` hands the library, so this would
    fail if the provider signed with anything of its own.
    """
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx))
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    assert key == requirer_charm_manual.PRIVATE_KEY
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    for certificate in assigned:
        assert certificate.certificate.matches_private_key(requirer_charm_manual.PRIVATE_KEY)


def test_the_library_keeps_no_key_secret(ctx: _Ctx, mocked: None):
    """A charm-supplied key means the library manages no key secret of its own.

    Only the certificate secrets should exist. This is why the old API's key-seeding helper
    had to be *not* used for this charm -- the library would delete the secret it seeded.
    """
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx))
    labels = [s.label for s in state.secrets if s.label]
    assert labels
    assert not [label for label in labels if "-private-key-" in label]
    assert len([label for label in labels if "-certificate-" in label]) == len(
        requirer_charm_manual.REQUESTS
    )


def test_integrated_means_asked_but_unanswered(ctx: _Ctx, mocked: None):
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx), end="integrated")
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate_signing_request.common_name for c in csrs} == REQUESTED
    assert not assigned
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_a_denied_request(ctx: _Ctx, mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.denied()
    )
    state = remote.integrate(ctx, ops.testing.State.from_context(ctx))
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        errors = manager.charm.certificates.get_request_errors()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {e.certificate_signing_request.common_name for e in errors} == REQUESTED
    assert not assigned
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_renewal_does_not_rotate_a_charm_supplied_key(ctx: _Ctx, mocked: None):
    """Renewal replaces the certificate, not the key -- and the charm owns the key here."""
    stale = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.renewing()
    )
    state = stale.integrate(ctx, ops.testing.State.from_context(ctx), end="published")
    with ctx(ctx.on.update_status(), state) as manager:
        state = manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
        was_stale = {str(c.certificate) for c in assigned}
    state = stale.run_changed(ctx, state)  # the safety net re-requests
    fresh = tls_certificates_testing.RemoteProvider("certificates")
    state = fresh.publish(state)
    state = fresh.run_changed(ctx, state)
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    assert key == requirer_charm_manual.PRIVATE_KEY  # unchanged
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert {str(c.certificate) for c in assigned}.isdisjoint(was_stale)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
