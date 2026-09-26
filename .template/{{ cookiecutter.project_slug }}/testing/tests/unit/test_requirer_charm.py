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

"""Tests for the {{ cookiecutter.project_slug }} testing library from a requirer charm perspective.

A requirer charm is tested with a ``RemoteProvider`` -- the remote plays the opposite role.
These are the tests a charm author would write, so they only use the package's public API and
never read relation data. The remote's own contract is tested in ``test_testing.py``.
"""

from __future__ import annotations

import typing

import ops.testing
import pytest

from charmlibs.interfaces import {{ cookiecutter.__pkg }}_testing as {{ cookiecutter.__pkg }}_testing

if typing.TYPE_CHECKING:
    _Ctx: typing.TypeAlias = ops.testing.Context[ops.CharmBase]

REMOTE = {{ cookiecutter.__pkg }}_testing.RemoteProvider('endpoint')


def test_requirer_no_relation(requirer_ctx: _Ctx, mocked: None):
    """Test requirer charm without any relation as a sanity check."""
    with requirer_ctx(requirer_ctx.on.update_status(), ops.testing.State(leader=True)) as manager:
        manager.run()
    # FIXME: Assert something about the charm.


def test_requirer_settled(requirer_ctx: _Ctx, mocked: None):
    """Test requirer charm once the whole conversation has happened.

    ``integrate``'s default ``end="received"`` adds the relation, runs the charm for the
    events Juju fires on integration, writes the provider's data, and runs the charm again so
    that it reconciles against it.
    """
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = REMOTE.integrate(requirer_ctx, state_in)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_requirer_waiting_for_an_answer(requirer_ctx: _Ctx, mocked: None):
    """Test requirer charm when it has asked but nobody has answered yet."""
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state = REMOTE.integrate(requirer_ctx, state_in, end='integrated')
    state_out = requirer_ctx.run(requirer_ctx.on.update_status(), state)
    # FIXME: Assert something -- a charm usually reports Blocked or Waiting here.
    del state_out


def test_requirer_relation_variant(requirer_ctx: _Ctx, mocked: None):
    """Test requirer charm against a provider behaving in some non-default way."""
    # FIXME: construct the remote with some non-default argument, once the library has one.
    remote = {{ cookiecutter.__pkg }}_testing.RemoteProvider('endpoint')
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_requirer_later_turn_of_the_conversation(requirer_ctx: _Ctx, mocked: None):
    """Test requirer charm after something makes it ask for something different.

    ``publish`` and ``run_changed`` are the two moves that drive every turn after the first.
    """
    state = REMOTE.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    state = requirer_ctx.run(requirer_ctx.on.config_changed(), state)
    state = REMOTE.publish(state)
    state_out = REMOTE.run_changed(requirer_ctx, state)
    # FIXME: Assert something about the charm's use of the library object.
    del state_out


def test_requirer_relation_broken(requirer_ctx: _Ctx, mocked: None):
    """``get_relation`` is the escape hatch for the events the other methods don't cover."""
    state = REMOTE.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    state_out = requirer_ctx.run(
        requirer_ctx.on.relation_broken(REMOTE.get_relation(state)), state
    )
    # FIXME: Assert something about the charm's use of the library object.
    del state_out


@pytest.mark.skip(reason='FIXME: fill this in, or delete it if one integrate is enough.')
def test_requirer_needs_a_second_round():
    """``end="received"`` settles the conversation ``integrate`` ran, and no more.

    Where the charm publishes in *response* to what it received, the provider hasn't answered
    that yet, so reaching a fixed point takes another ``publish`` and ``run_changed``. Whether
    it's needed is a property of the interface and the charm, so check by looking: run the
    extra round and compare.
    """
