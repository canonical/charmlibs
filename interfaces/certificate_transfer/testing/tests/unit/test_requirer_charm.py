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

"""Tests for the certificate_transfer testing library from a requirer charm perspective.

A requirer charm is tested with a ``RemoteProvider`` -- the remote plays the opposite role.
These are the tests a charm author would write, so they only use the package's public API
and never read relation data. The remote's own contract is tested in ``test_testing.py``.
"""

from __future__ import annotations

import typing

import ops.testing

from charmlibs.interfaces import certificate_transfer_testing as certificate_transfer_testing

if typing.TYPE_CHECKING:
    import pytest

    import requirer_charm

    _Ctx: typing.TypeAlias = ops.testing.Context[requirer_charm.RequirerCharm]

CA_CERTS = certificate_transfer_testing.RemoteProvider('certificates')
ROOT = '-----BEGIN CERTIFICATE-----\nroot\n-----END CERTIFICATE-----'
INTERMEDIATE = '-----BEGIN CERTIFICATE-----\nintermediate\n-----END CERTIFICATE-----'


def test_requirer_no_relation(requirer_ctx: _Ctx, mocked: None):
    """Without a relation there are no CA certificates to have."""
    with requirer_ctx(requirer_ctx.on.update_status(), ops.testing.State(leader=True)) as manager:
        state_out = manager.run()
        assert manager.charm.certificates is None
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_settled(requirer_ctx: _Ctx, mocked: None):
    """Once the whole conversation has happened, the charm has the provider's CA.

    ``integrate``'s default ``end="received"`` adds the relation, runs the charm for the
    events Juju fires on integration -- which is where it advertises the version of the wire
    format it understands -- writes the provider's certificates, and runs the charm again so
    that it reconciles.
    """
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = CA_CERTS.integrate(requirer_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.certificates == set(CA_CERTS.certificates)


def test_requirer_nothing_transferred_yet(requirer_ctx: _Ctx, mocked: None):
    """The relation exists, and nobody has transferred anything over it."""
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = CA_CERTS.integrate(requirer_ctx, state_in, end='integrated')
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assert manager.charm.certificates is None
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_certificates_not_yet_seen(requirer_ctx: _Ctx, mocked: None):
    """``end="published"`` puts the certificates on the wire without the charm running again.

    The charm can still read them -- relation data is relation data -- so this is the state
    to use where the test's own act step is the event that should pick them up.
    """
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = CA_CERTS.integrate(requirer_ctx, state_in, end='published')
    assert isinstance(state.unit_status, ops.testing.BlockedStatus)
    state_out = CA_CERTS.run_changed(requirer_ctx, state)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_requirer_several_certificates(requirer_ctx: _Ctx, mocked: None):
    """``certificates`` is the set the provider transfers; the charm gets all of it."""
    remote = certificate_transfer_testing.RemoteProvider(
        'certificates', certificates=[ROOT, INTERMEDIATE]
    )
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.certificates == {ROOT, INTERMEDIATE}


def test_requirer_provider_has_nothing_to_transfer(requirer_ctx: _Ctx, mocked: None):
    """An empty set is an answer, and it is empty -- not the same as no answer at all."""
    remote = certificate_transfer_testing.RemoteProvider('certificates', certificates=[])
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assert manager.charm.certificates is None
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_old_provider_uses_the_v0_format(requirer_ctx: _Ctx, mocked: None):
    """``interface_version=0`` models a provider charm that predates v1 of the interface.

    The library falls back to reading the provider's *unit* databag, so a modern requirer
    charm still gets its certificates. This is the one case a leader charm can't reach by
    itself, since it always advertises version 1.
    """
    remote = certificate_transfer_testing.RemoteProvider('certificates', interface_version=0)
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assert manager.charm.certificates == set(remote.certificates)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_requirer_non_leader_is_answered_in_the_v0_format(
    requirer_ctx: _Ctx, mocked: None, caplog: pytest.LogCaptureFixture
):
    """A non-leader requirer can't advertise version 1, so it is taken for an old one.

    It still receives the certificates, through the same v0 fallback. The remote logs which
    format it chose and why, rather than raising: a test that wants a non-leader unit for
    some unrelated reason shouldn't be obstructed.
    """
    state_in = ops.testing.State.from_context(requirer_ctx, leader=False)
    state = CA_CERTS.integrate(requirer_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    assert 'leader=True' in caplog.text
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.certificates == set(CA_CERTS.certificates)


def test_requirer_several_providers(requirer_ctx: _Ctx, mocked: None):
    """A remote stands for one application, so several issuers take one remote each."""
    remotes = [
        certificate_transfer_testing.RemoteProvider(
            'certificates', remote_app_name=name, certificates=[pem]
        )
        for name, pem in (('root-ca', ROOT), ('intermediate-ca', INTERMEDIATE))
    ]
    state = ops.testing.State.from_context(requirer_ctx, leader=True)
    for remote in remotes:
        state = remote.integrate(requirer_ctx, state)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.certificates == {ROOT, INTERMEDIATE}


def test_requirer_later_turn_of_the_conversation(requirer_ctx: _Ctx, mocked: None):
    """``publish`` and ``run_changed`` drive every turn after the first.

    Here the provider rotates its CA. A second remote with the same endpoint and application
    name stands for the same application transferring something else.
    """
    state = CA_CERTS.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    rotated = certificate_transfer_testing.RemoteProvider('certificates', certificates=[ROOT])
    state = rotated.publish(state)
    state = rotated.run_changed(requirer_ctx, state)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        # The certificate it used to have is gone, not merely added to.
        assert manager.charm.certificates == {ROOT}


def test_requirer_relation_broken(requirer_ctx: _Ctx, mocked: None):
    """``get_relation`` is the escape hatch for the events the other methods don't cover."""
    state = CA_CERTS.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with requirer_ctx(
        requirer_ctx.on.relation_broken(CA_CERTS.get_relation(state)), state
    ) as manager:
        state_out = manager.run()
        assert manager.charm.certificates is None
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)
