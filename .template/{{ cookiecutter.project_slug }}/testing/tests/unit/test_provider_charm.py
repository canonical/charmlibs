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

"""Tests for the {{ cookiecutter.project_slug }} testing library from a provider charm perspective.

A provider charm is tested with a ``RemoteRequirer`` -- the remote plays the opposite role.
These are the tests a charm author would write, so they only use the package's public API and
never read relation data. The remote's own contract is tested in ``test_testing.py``.
"""

from __future__ import annotations

import typing

import ops.testing

from charmlibs.interfaces import {{ cookiecutter.__pkg }}_testing as {{ cookiecutter.__pkg }}_testing

if typing.TYPE_CHECKING:
    _Ctx: typing.TypeAlias = ops.testing.Context[ops.CharmBase]

REMOTE = {{ cookiecutter.__pkg }}_testing.RemoteRequirer('endpoint')


def test_provider_no_relation(provider_ctx: _Ctx, mocked: None):
    """Test provider charm without any relation as a sanity check."""
    with provider_ctx(provider_ctx.on.update_status(), ops.testing.State(leader=True)) as manager:
        manager.run()
    # FIXME: Assert something about the charm.


def test_provider_nothing_to_read_yet(provider_ctx: _Ctx, mocked: None):
    """Test provider charm when the requirer hasn't asked for anything yet."""
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = REMOTE.integrate(provider_ctx, state_in, end='integrated')
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_provider_has_answered(provider_ctx: _Ctx, mocked: None):
    """Test provider charm once the whole conversation has happened.

    ``integrate``'s default ``end="received"`` adds the relation, runs the charm for the
    events Juju fires on integration, writes the requirer's request, and runs the charm again
    so that it answers.
    """
    state_in = ops.testing.State.from_context(provider_ctx, leader=True)
    state = REMOTE.integrate(provider_ctx, state_in)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_provider_relation_variant(provider_ctx: _Ctx, mocked: None):
    """Test provider charm against a requirer asking for something non-default."""
    # FIXME: construct the remote with some non-default argument, once the library has one.
    remote = {{ cookiecutter.__pkg }}_testing.RemoteRequirer('endpoint')
    state = remote.integrate(
        provider_ctx, ops.testing.State.from_context(provider_ctx, leader=True)
    )
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_provider_several_requirers(provider_ctx: _Ctx, mocked: None):
    """A remote stands for one application, so aggregating over several takes one each.

    FIXME: delete this test if the library supports only one remote per endpoint, in which
    case ``_check_can_add`` should be overridden to raise ``ValueError``.
    """
    remotes = [
        {{ cookiecutter.__pkg }}_testing.RemoteRequirer('endpoint', remote_app_name=f'app{n}')
        for n in range(2)
    ]
    state = ops.testing.State.from_context(provider_ctx, leader=True)
    for remote in remotes:
        state = remote.integrate(provider_ctx, state)
    # FIXME: Assert something about the charm's use of the library object.


def test_provider_relation_broken(provider_ctx: _Ctx, mocked: None):
    """``get_relation`` is the escape hatch for the events the other methods don't cover."""
    state = REMOTE.integrate(
        provider_ctx, ops.testing.State.from_context(provider_ctx, leader=True)
    )
    state_out = provider_ctx.run(
        provider_ctx.on.relation_broken(REMOTE.get_relation(state)), state
    )
    # FIXME: Assert something about the charm's use of the library object.
    del state_out
