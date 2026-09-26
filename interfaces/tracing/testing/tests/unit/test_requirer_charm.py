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

"""Tests for the tracing testing library from a requirer charm perspective.

A requirer charm is tested with a ``RemoteProvider`` -- the remote plays the opposite role.
These are the tests a charm author would write, so they only use the package's public API
and never read relation data. The remote's own contract is tested in ``test_testing.py``.
"""

from __future__ import annotations

import typing

import ops.testing

from charmlibs.interfaces import tracing_testing as tracing_testing

if typing.TYPE_CHECKING:
    import pytest

    import requirer_charm
    import requirer_charm_multi

    _Ctx: typing.TypeAlias = ops.testing.Context[requirer_charm.RequirerCharm]
    _MultiCtx: typing.TypeAlias = ops.testing.Context[requirer_charm_multi.MultiRequirerCharm]

TRACING = tracing_testing.RemoteProvider('tracing')
OTLP_ONLY = tracing_testing.RemoteProvider('tracing', supported_protocols=['otlp_http'])
SECURE = tracing_testing.RemoteProvider('tracing', tls=True)


def test_requirer_no_relation(requirer_ctx: _Ctx, mocked: None):
    """Without a tracing relation there is nothing to be ready for."""
    with requirer_ctx(requirer_ctx.on.update_status(), ops.testing.State(leader=True)) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints is None
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_settled(requirer_ctx: _Ctx, mocked: None):
    """Once the whole conversation has happened, the charm has a URL per protocol.

    ``integrate``'s default ``end="received"`` adds the relation, runs the charm for the
    events Juju fires on integration -- which is where it publishes its request -- writes
    the provider's answer to that request, and runs the charm again so that it reconciles.
    """
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = TRACING.integrate(requirer_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'otlp_http': 'http://tracing.example.com:4318',
            'zipkin': 'http://tracing.example.com:9411',
        }


def test_requirer_waiting_for_an_answer(requirer_ctx: _Ctx, mocked: None):
    """The charm has asked, and nobody has answered yet."""
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = TRACING.integrate(requirer_ctx, state_in, end='integrated')
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints is None
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_answer_not_yet_seen(requirer_ctx: _Ctx, mocked: None):
    """``end="published"`` puts the answer on the wire without the charm having run again.

    The charm can still read it -- relation data is relation data -- so this is the state to
    use where the test's own act step is the event that should pick the answer up.
    """
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = TRACING.integrate(requirer_ctx, state_in, end='published')
    assert isinstance(state.unit_status, ops.testing.BlockedStatus)
    state_out = TRACING.run_changed(requirer_ctx, state)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_requirer_provider_supports_only_some_protocols(requirer_ctx: _Ctx, mocked: None):
    """A provider answers with the protocols it has and omits the rest."""
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = OTLP_ONLY.integrate(requirer_ctx, state_in)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints == {'otlp_http': 'http://tracing.example.com:4318'}
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_behind_tls(requirer_ctx: _Ctx, mocked: None):
    """``tls=True`` makes the HTTP protocols' URLs https, which charms often branch on."""
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = SECURE.integrate(requirer_ctx, state_in)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'otlp_http': 'https://tracing.example.com:4318',
            'zipkin': 'https://tracing.example.com:9411',
        }


def test_requirer_custom_host(requirer_ctx: _Ctx, mocked: None):
    """``host`` is there for a charm that cares which address it was given."""
    remote = tracing_testing.RemoteProvider('tracing', host='tempo.example.org')
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'otlp_http': 'http://tempo.example.org:4318',
            'zipkin': 'http://tempo.example.org:9411',
        }


def test_requirer_non_leader_never_asks(
    requirer_ctx: _Ctx, mocked: None, caplog: pytest.LogCaptureFixture
):
    """A non-leader requirer can't write its request, so there is nothing to answer.

    The remote logs a hint rather than raising, because a test that wants a non-leader unit
    for some unrelated reason shouldn't be obstructed.
    """
    state_in = ops.testing.State.from_context(requirer_ctx, leader=False)
    state = TRACING.integrate(requirer_ctx, state_in)
    assert isinstance(state.unit_status, ops.testing.BlockedStatus)
    assert 'leader=True' in caplog.text


def test_requirer_later_turn_of_the_conversation(requirer_ctx: _Ctx, mocked: None):
    """``publish`` and ``run_changed`` drive every turn after the first.

    Here the backend is reconfigured to stop serving zipkin. A second remote with the same
    endpoint and application name stands for the same application behaving differently.
    """
    state = TRACING.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    state = OTLP_ONLY.publish(state)
    state_out = OTLP_ONLY.run_changed(requirer_ctx, state)
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_relation_broken(requirer_ctx: _Ctx, mocked: None):
    """``get_relation`` is the escape hatch for the events the other methods don't cover."""
    state = TRACING.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with requirer_ctx(
        requirer_ctx.on.relation_broken(TRACING.get_relation(state)), state
    ) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints is None
    assert isinstance(state_out.unit_status, ops.testing.BlockedStatus)


def test_requirer_several_providers(multi_requirer_ctx: _MultiCtx, mocked: None):
    """A remote stands for one application, so several backends take one remote each."""
    remotes = [
        tracing_testing.RemoteProvider('tracing', remote_app_name=name, host=f'{name}.example.com')
        for name in ('tempo', 'jaeger')
    ]
    state = ops.testing.State.from_context(multi_requirer_ctx, leader=True)
    for remote in remotes:
        state = remote.integrate(multi_requirer_ctx, state)
    with multi_requirer_ctx(multi_requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'tempo': 'http://tempo.example.com:4318',
            'jaeger': 'http://jaeger.example.com:4318',
        }
