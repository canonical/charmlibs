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

"""Tests for a requirer charm holding a certificate in each of the library's two scopes.

Mode.APP_AND_UNIT is where the old API needed the most arrangement: one key secret per scope,
seeded with the key the fixture had signed both scopes' requests with. Deriving the answer
removes all of it -- the charm generates a key per scope itself, and the provider signs what
each scope published.
"""

from __future__ import annotations

import typing

import ops
import ops.testing
import pytest

import requirer_charm_app_and_unit as charm_module
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

CERTS = tls_certificates_testing.RemoteProvider("certificates")

_Ctx: typing.TypeAlias = "ops.testing.Context[charm_module.AppAndUnitRequirerCharm]"


@pytest.fixture()
def ctx() -> _Ctx:
    return ops.testing.Context(charm_module.AppAndUnitRequirerCharm, meta=charm_module.META)


def test_the_happy_path(ctx: _Ctx, mocked: None):
    state_out = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_both_scopes_get_their_certificate(ctx: _Ctx, mocked: None):
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        app, app_key = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.APP
        )
        unit, unit_key = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.UNIT
        )
    assert {c.certificate.common_name for c in app} == {charm_module.APP_REQUEST.common_name}
    assert {c.certificate.common_name for c in unit} == {charm_module.UNIT_REQUEST.common_name}
    # A separate key per scope, and each scope's certificates bound to its own key.
    assert app_key is not None
    assert unit_key is not None
    assert app_key != unit_key
    for certificate in app:
        assert certificate.certificate.matches_private_key(app_key)
    for certificate in unit:
        assert certificate.certificate.matches_private_key(unit_key)


def test_one_key_secret_per_scope(ctx: _Ctx, mocked: None):
    """The library keeps a key per scope, which is why seeding them was awkward before."""
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    keys = [s for s in state.secrets if s.label and "-private-key-" in s.label]
    assert len(keys) == 2
    assert {s.owner for s in keys} == {"app", "unit"}


def test_a_non_leader_holds_only_its_unit_certificate(ctx: _Ctx, mocked: None):
    """A non-leader can act on the unit scope only, per the library's 1.10.1 fix.

    It can reach neither the application key nor the application certificates, and must not
    take the unit scope down with the application one.
    """
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=False))
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        unit, unit_key = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.UNIT
        )
        assert manager.charm.app_certs is None
    assert unit_key is not None
    assert {c.certificate.common_name for c in unit} == {charm_module.UNIT_REQUEST.common_name}
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_renewal_of_both_scopes(ctx: _Ctx, mocked: None):
    stale = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.renewing()
    )
    state = stale.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        app, _ = manager.charm.certificates.get_assigned_certificates(tls_certificates.Mode.APP)
        unit, _ = manager.charm.certificates.get_assigned_certificates(tls_certificates.Mode.UNIT)
        was_stale = {str(c.certificate) for c in (*app, *unit)}
    state = stale.run_changed(ctx, state)  # the safety net re-requests both scopes
    fresh = tls_certificates_testing.RemoteProvider("certificates")
    state = fresh.publish(state)
    state = fresh.run_changed(ctx, state)
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        app, _ = manager.charm.certificates.get_assigned_certificates(tls_certificates.Mode.APP)
        unit, _ = manager.charm.certificates.get_assigned_certificates(tls_certificates.Mode.UNIT)
    assert {c.certificate.common_name for c in app} == {charm_module.APP_REQUEST.common_name}
    assert {c.certificate.common_name for c in unit} == {charm_module.UNIT_REQUEST.common_name}
    assert {str(c.certificate) for c in (*app, *unit)}.isdisjoint(was_stale)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_a_denied_application_request(ctx: _Ctx, mocked: None):
    """Mixed outcomes across scopes: the unit certificate is issued, the app one refused."""
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        outcome=lambda request: (
            tls_certificates_testing.Outcome.denied()
            if request.common_name == charm_module.APP_REQUEST.common_name
            else tls_certificates_testing.Outcome.issued()
        ),
    )
    state = remote.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        app, _ = manager.charm.certificates.get_assigned_certificates(tls_certificates.Mode.APP)
        unit, _ = manager.charm.certificates.get_assigned_certificates(tls_certificates.Mode.UNIT)
        errors = manager.charm.certificates.get_request_errors()
    assert not app
    assert {c.certificate.common_name for c in unit} == {charm_module.UNIT_REQUEST.common_name}
    assert {e.certificate_signing_request.common_name for e in errors} == {
        charm_module.APP_REQUEST.common_name
    }
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
