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

"""Tests for the tracing testing library from a provider charm perspective.

A provider charm is tested with a ``RemoteRequirer`` -- the remote plays the opposite role.
These are the tests a charm author would write, so they only use the package's public API
and never read relation data. The remote's own contract is tested in ``test_testing.py``.
"""

from __future__ import annotations

import typing

import ops.testing

# The aliased form keeps these on separate lines, which a namespace package split across
# two distributions needs for pyright to resolve both halves.
from charmlibs.interfaces import tracing as tracing
from charmlibs.interfaces import tracing_testing as tracing_testing

if typing.TYPE_CHECKING:
    import provider_charm

    _Ctx: typing.TypeAlias = ops.testing.Context[provider_charm.ProviderCharm]

WORKLOAD = tracing_testing.RemoteRequirer('tracing')
GRPC_WORKLOAD = tracing_testing.RemoteRequirer('tracing', protocols=['otlp_grpc'])


def test_provider_no_relation(provider_ctx: _Ctx, mocked: None):
    """Nobody is asking for anything, so nothing is enabled."""
    with provider_ctx(provider_ctx.on.update_status(), ops.testing.State(leader=True)) as manager:
        state_out = manager.run()
        assert manager.charm.enabled is None
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_provider_nothing_to_read_yet(provider_ctx: _Ctx, mocked: None):
    """The relation exists, but the requirer hasn't published its request."""
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = WORKLOAD.integrate(provider_ctx, state_in, end='integrated')
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.enabled is None


def test_provider_request_not_yet_seen(provider_ctx: _Ctx, mocked: None):
    """``end="published"`` leaves the request on the wire for the test's own act step."""
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = WORKLOAD.integrate(provider_ctx, state_in, end='published')
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_http']


def test_provider_has_answered(provider_ctx: _Ctx, mocked: None):
    """Once the whole conversation has happened, the charm has answered the request.

    ``integrate``'s default ``end="received"`` adds the relation, runs the charm for the
    events Juju fires on integration, writes the requirer's request, and runs the charm
    again so that it answers.
    """
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = WORKLOAD.integrate(provider_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_http']


def test_provider_answers_the_protocol_asked_for(provider_ctx: _Ctx, mocked: None):
    """``protocols`` is what the simulated requirer asks for."""
    state = GRPC_WORKLOAD.integrate(
        provider_ctx, ops.testing.State.from_context(provider_ctx, leader=True)
    )
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_grpc']


def test_provider_non_leader_does_not_publish(provider_ctx: _Ctx, mocked: None):
    """Publishing is leader-only, so this charm reads the request and does nothing."""
    state_in = ops.testing.State.from_context(provider_ctx, leader=False)
    state = WORKLOAD.integrate(provider_ctx, state_in)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_http']
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)


def test_provider_several_requirers(provider_ctx: _Ctx, mocked: None):
    """A remote stands for one application, so aggregating over several takes one each."""
    wanted: list[tuple[str, tracing.ReceiverProtocol]] = [
        ('charm-traces', 'otlp_http'),
        ('workload-traces', 'otlp_grpc'),
    ]
    remotes = [
        tracing_testing.RemoteRequirer('tracing', remote_app_name=name, protocols=[protocol])
        for name, protocol in wanted
    ]
    state = ops.testing.State.from_context(provider_ctx, leader=True)
    for remote in remotes:
        state = remote.integrate(provider_ctx, state)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_grpc', 'otlp_http']


def test_provider_later_turn_of_the_conversation(provider_ctx: _Ctx, mocked: None):
    """``publish`` and ``run_changed`` drive every turn after the first.

    Here the workload is reconfigured to send traces over gRPC instead. A second remote with
    the same endpoint and application name stands for the same application asking anew.
    """
    state = WORKLOAD.integrate(
        provider_ctx, ops.testing.State.from_context(provider_ctx, leader=True)
    )
    state = GRPC_WORKLOAD.publish(state)
    state = GRPC_WORKLOAD.run_changed(provider_ctx, state)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_grpc']


def test_provider_relation_broken(provider_ctx: _Ctx, mocked: None):
    """``get_relation`` is the escape hatch for the events the other methods don't cover."""
    state = WORKLOAD.integrate(
        provider_ctx, ops.testing.State.from_context(provider_ctx, leader=True)
    )
    state_out = provider_ctx.run(
        provider_ctx.on.relation_broken(WORKLOAD.get_relation(state)), state
    )
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
