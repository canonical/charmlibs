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

"""Tests for a requirer charm whose certificate belongs to the application."""

from __future__ import annotations

import typing

import ops
import ops.testing
import pytest

import requirer_charm_app
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

CERTS = tls_certificates_testing.RemoteProvider("certificates")
REQUESTED = {r.common_name for r in requirer_charm_app.REQUESTS}

_Ctx: typing.TypeAlias = "ops.testing.Context[requirer_charm_app.AppRequirerCharm]"


@pytest.fixture()
def ctx() -> _Ctx:
    return ops.testing.Context(requirer_charm_app.AppRequirerCharm, meta=requirer_charm_app.META)


def test_the_happy_path(ctx: _Ctx, mocked: None):
    """An application-scoped requirer must be the leader, since it writes app data."""
    state_out = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_the_requests_are_application_scoped(ctx: _Ctx, mocked: None):
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED


def test_the_key_secret_is_app_owned(ctx: _Ctx, mocked: None):
    """Mode.APP keeps the key in an app-owned secret, at a distinct label.

    The library derives that label itself, so a test never has to name it -- but the owner is
    worth pinning, because it is what makes the key readable by a new leader.
    """
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    keys = [s for s in state.secrets if s.label and "-private-key-" in s.label]
    assert len(keys) == 1
    assert keys[0].owner == "app"
    assert "-private-key-app-" in (keys[0].label or "")


def test_a_non_leader_cannot_ask(ctx: _Ctx, mocked: None):
    """An application-scoped requirer writes app data, which a non-leader cannot do.

    So it asks for nothing and gets nothing. The package warns about this when it publishes
    into an empty relation, because it is otherwise invisible in the resulting state and
    easily mistaken for a bug in the charm.
    """
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx, leader=False))
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assert manager.charm.certs is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_the_non_leader_warning(ctx: _Ctx, mocked: None, caplog: pytest.LogCaptureFixture):
    """The hint that names the specific, likely reason for the empty relation above."""
    state = CERTS.integrate(
        ctx, ops.testing.State.from_context(ctx, leader=False), end="integrated"
    )
    caplog.clear()
    CERTS.publish(state)
    assert "leader=True" in caplog.text


def test_renewal(ctx: _Ctx, mocked: None):
    stale = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.renewing()
    )
    state = stale.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
    state = stale.run_changed(ctx, state)  # the safety net re-requests
    fresh = tls_certificates_testing.RemoteProvider("certificates")
    state = fresh.publish(state)
    state = fresh.run_changed(ctx, state)
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
