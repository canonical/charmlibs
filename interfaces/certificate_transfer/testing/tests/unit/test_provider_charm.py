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

"""Tests for the certificate_transfer testing library from a provider charm perspective.

A provider charm is tested with a ``RemoteRequirer`` -- the remote plays the opposite role.
These are the tests a charm author would write, so they only use the package's public API
and never read relation data. The remote's own contract is tested in ``test_testing.py``.

The charm under test is paired with a requirer charm here and there, rather than only having
its relation data inspected, because what a provider charm publishes is only interesting
inasmuch as a requirer can read it back.
"""

from __future__ import annotations

import typing

import ops.testing

import provider_charm
import requirer_charm
from charmlibs.interfaces import certificate_transfer_testing as certificate_transfer_testing

if typing.TYPE_CHECKING:
    _Ctx: typing.TypeAlias = ops.testing.Context[provider_charm.ProviderCharm]

CLIENT = certificate_transfer_testing.RemoteRequirer('send-ca-cert')
OLD_CLIENT = certificate_transfer_testing.RemoteRequirer('send-ca-cert', interface_version=0)


def test_provider_no_relation(provider_ctx: _Ctx, mocked: None):
    """Nobody is asking, so there is nothing to transfer to."""
    with provider_ctx(provider_ctx.on.update_status(), ops.testing.State(leader=True)) as manager:
        state_out = manager.run()
        assert manager.charm.transferred is True
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_provider_has_transferred(provider_ctx: _Ctx, mocked: None):
    """Once the whole conversation has happened, the charm's CA is on the wire.

    ``integrate``'s default ``end="received"`` adds the relation, runs the charm for the
    events Juju fires on integration, writes the requirer's advertised version, and runs the
    charm again so that it answers in that version's format.
    """
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = CLIENT.integrate(provider_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    assert _read_back(state) == {provider_charm.CA_CERT}


def test_provider_before_the_requirer_has_spoken(provider_ctx: _Ctx, mocked: None):
    """``end="integrated"`` is the state where nobody on the other end has said anything.

    This charm transfers on ``relation-joined``, so it has already written by then -- in the
    v0 format, because the requirer's ``version`` isn't on the wire yet. That is Juju's own
    ordering rather than an artefact of this package: a provider can be joined before the
    requirer's application data has propagated.
    """
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = CLIENT.integrate(provider_ctx, state_in, end='integrated')
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    assert _read_back(state) == {provider_charm.CA_CERT}


def test_provider_request_not_yet_seen(provider_ctx: _Ctx, mocked: None):
    """``end="published"`` leaves the requirer's version on the wire for the test's act step."""
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = CLIENT.integrate(provider_ctx, state_in, end='published')
    state_out = CLIENT.run_changed(provider_ctx, state)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    assert _read_back(state_out) == {provider_charm.CA_CERT}


def test_provider_answers_an_old_requirer(provider_ctx: _Ctx, mocked: None):
    """``interface_version=0`` models a requirer charm that predates v1 of the interface.

    It advertises nothing, so the charm under test keeps writing the v0 format, which is
    what the library's fallback exists for.
    """
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = OLD_CLIENT.integrate(provider_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    assert _read_back(state) == {provider_charm.CA_CERT}


def test_provider_non_leader_transfers_nothing(provider_ctx: _Ctx, mocked: None):
    """Transferring is leader-only, so this charm reads the request and does nothing."""
    state_in = ops.testing.State.from_context(provider_ctx, leader=False)
    state = CLIENT.integrate(provider_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    assert _read_back(state) == set()


def test_provider_several_requirers(provider_ctx: _Ctx, mocked: None):
    """A remote stands for one application, so several clients take one remote each."""
    remotes = [
        certificate_transfer_testing.RemoteRequirer('send-ca-cert', remote_app_name=name)
        for name in ('workload', 'dashboard')
    ]
    state = ops.testing.State.from_context(provider_ctx, leader=True)
    for remote in remotes:
        state = remote.integrate(provider_ctx, state)
    for remote in remotes:
        assert _read_back(state, remote) == {provider_charm.CA_CERT}


def test_provider_relation_broken(provider_ctx: _Ctx, mocked: None):
    """``get_relation`` is the escape hatch for the events the other methods don't cover."""
    state = CLIENT.integrate(
        provider_ctx, ops.testing.State.from_context(provider_ctx, leader=True)
    )
    state_out = provider_ctx.run(
        provider_ctx.on.relation_broken(CLIENT.get_relation(state)), state
    )
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def _read_back(
    state: ops.testing.State,
    remote: certificate_transfer_testing.RemoteRequirer = CLIENT,
) -> set[str]:
    """What a real requirer charm would see, by running one against the provider's databags.

    Reading the provider's relation data directly would mean knowing the wire format, and
    knowing which of the interface's two formats to look in. Running the library's own
    requirer over the same relation asks the question a charm author actually has -- "did
    this arrive?" -- and answers it the same way for both formats.
    """
    relation = remote.get_relation(state)
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    # The two sides swap over: what the provider charm wrote locally is what the requirer
    # charm reads remotely, and vice versa.
    mirrored = ops.testing.Relation(
        'certificates',
        interface='certificate_transfer',
        remote_app_name='provider',
        local_app_data=dict(relation.remote_app_data),
        remote_app_data=dict(relation.local_app_data),
        remote_units_data={0: dict(relation.local_unit_data)},
    )
    with ctx(ctx.on.update_status(), ops.testing.State(leader=True, relations=[mirrored])) as m:
        m.run()
        return m.charm.certificates or set()
