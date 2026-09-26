# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the remote classes' own contract.

These read relation data directly, which a charm test should never do -- the point of the
package is that charm tests don't have to. Here it is the subject.
"""

from __future__ import annotations

import dataclasses
import typing

import ops
import ops.testing
import pytest

from charmlibs.interfaces import example_interface_testing as example_interface_testing

if typing.TYPE_CHECKING:
    _Ctx: typing.TypeAlias = ops.testing.Context[ops.CharmBase]

_Remote: typing.TypeAlias = (
    example_interface_testing.RemoteProvider | example_interface_testing.RemoteRequirer
)

CLASSES: list[type[_Remote]] = [
    example_interface_testing.RemoteProvider,
    example_interface_testing.RemoteRequirer,
]
REMOTES = [cls('endpoint') for cls in CLASSES]
IDS = ['RemoteProvider', 'RemoteRequirer']


def _bare_state(remote: _Remote) -> ops.testing.State:
    """A bare relation for ``remote``, built from its own attributes so the two agree."""
    relation = ops.testing.Relation(
        remote.endpoint,
        interface='example-interface',
        remote_app_name=remote.remote_app_name,
    )
    return ops.testing.State(leader=True, relations=[relation])


# ----------------------------------------------------------- construction and identity


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_endpoint_is_required_and_positional(cls: type[_Remote]):
    """endpoint must be passable positionally or by keyword, and must be required."""
    assert cls('endpoint').endpoint == 'endpoint'
    assert cls(endpoint='endpoint').endpoint == 'endpoint'
    with pytest.raises(TypeError):
        cls()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_every_other_argument_is_keyword_only(cls: type[_Remote]):
    """All other arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        cls('endpoint', 'remote')  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_endpoint_and_remote_app_name_are_readable(cls: type[_Remote]):
    """Both must be readable, so a hand-built bare Relation can agree with them."""
    assert cls('endpoint').endpoint == 'endpoint'
    assert cls('endpoint').remote_app_name == 'remote'
    assert cls('endpoint', remote_app_name='other').remote_app_name == 'other'


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_remotes_are_immutable(remote: _Remote):
    """The arguments given at construction cannot be changed afterwards.

    Read-only properties rather than a frozen dataclass, so the error is AttributeError.
    FIXME: assert the same of every argument this library adds.
    """
    with pytest.raises(AttributeError):
        remote.endpoint = 'other'  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        remote.remote_app_name = 'other'  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_repr_shows_the_arguments_the_caller_chose(remote: _Remote):
    """pytest derives parametrize IDs from it, so it must be short and self-describing."""
    assert repr(remote) == f"{type(remote).__name__}('endpoint')"
    other = type(remote)('endpoint', remote_app_name='other')
    assert repr(other) == f"{type(remote).__name__}('endpoint', remote_app_name='other')"


# ------------------------------------------------------------------ the mocked() scope


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
@pytest.mark.parametrize('method', ['integrate', 'publish', 'run_changed'])
def test_state_producing_methods_require_the_mocked_scope(
    remote: _Remote, method: str, requirer_ctx: _Ctx
):
    """Every library requires the scope, including the ones that mock nothing.

    A library that didn't would break every test written against it on the day it started
    mocking. Requiring it from the start makes introducing mocking a non-breaking change.
    """
    state = _bare_state(remote)
    args = (state,) if method == 'publish' else (requirer_ctx, state)
    with pytest.raises(RuntimeError, match='mocked'):
        getattr(remote, method)(*args)


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_get_relation_does_not_require_the_mocked_scope(remote: _Remote):
    """Assertions commonly run after the scope has closed, so this must work outside it."""
    state = _bare_state(remote)
    assert remote.get_relation(state).endpoint == remote.endpoint


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_mocked_is_reentrant(remote: _Remote):
    """A fixture and the test that uses it may each open a scope."""
    with example_interface_testing.mocked(), example_interface_testing.mocked():
        remote.publish(_bare_state(remote))
    # And the scope is properly closed again on the way out.
    with pytest.raises(RuntimeError, match='mocked'):
        remote.publish(_bare_state(remote))


# ---------------------------------------------------------------------- get_relation


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_get_relation_raises_when_there_is_no_relation(remote: _Remote):
    with pytest.raises(KeyError, match='no relation'):
        remote.get_relation(ops.testing.State())


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_get_relation_matches_on_the_remote_app_name_too(remote: _Remote):
    """A remote stands for one application on one endpoint, not for the endpoint."""
    mine = ops.testing.Relation(remote.endpoint, remote_app_name=remote.remote_app_name)
    theirs = ops.testing.Relation(remote.endpoint, remote_app_name='someone-else')
    state = ops.testing.State(relations=[mine, theirs])
    assert remote.get_relation(state).id == mine.id


# ------------------------------------------------------------------------- integrate


@pytest.mark.parametrize('end', ['integrated', 'published', 'received'])
def test_integrate_adds_the_relation(requirer_ctx: _Ctx, mocked: None, end: str):
    """FIXME: also assert what each value of end leaves on the wire."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State(leader=True), end=typing.cast('typing.Any', end)
    )
    relation = REMOTES[0].get_relation(state)
    assert relation.endpoint == REMOTES[0].endpoint
    assert relation.remote_app_name == REMOTES[0].remote_app_name


def test_integrate_adopts_a_bare_relation(requirer_ctx: _Ctx, mocked: None):
    """ops.testing.State.from_context puts one there for every endpoint in the metadata."""
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state_out = REMOTES[0].integrate(requirer_ctx, state_in)
    assert len(state_out.relations) == len(state_in.relations)


def test_integrate_rejects_an_invalid_end(requirer_ctx: _Ctx, mocked: None):
    with pytest.raises(ValueError, match='end must be'):
        REMOTES[0].integrate(
            requirer_ctx, ops.testing.State(), end=typing.cast('typing.Any', 'settled')
        )


def test_integrate_preserves_the_rest_of_the_state(requirer_ctx: _Ctx, mocked: None):
    """Everything the remote isn't responsible for is left as it is.

    FIXME: extend this with anything else your library touches. Other *relations* are
    covered by the publish test below rather than here, because integrate runs the charm and
    so every endpoint in the state has to be declared in the charm's metadata.
    """
    secret = ops.testing.Secret({'a': 'b'}, label='unrelated', owner='unit')
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True, secrets=[secret])
    state_out = REMOTES[0].integrate(requirer_ctx, state_in)
    assert {s.label for s in state_out.secrets} == {'unrelated'}
    assert state_out.leader is True


# --------------------------------------------------------------------------- publish


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_preserves_the_rest_of_the_state(remote: _Remote, mocked: None):
    """OP093: other relations, endpoints, secrets and config are preserved as-is."""
    other = ops.testing.Relation('other-endpoint', remote_app_data={'key': 'value'})
    secret = ops.testing.Secret({'a': 'b'}, label='unrelated', owner='unit')
    state = _bare_state(remote)
    state = dataclasses.replace(
        state,
        relations=[*state.relations, other],
        secrets=[secret],
        config={'foo': 'bar'},
    )
    out = remote.publish(state)
    published = next(r for r in out.relations if r.id == other.id)
    assert isinstance(published, ops.testing.Relation)
    assert published.remote_app_data == {'key': 'value'}
    assert {s.label for s in out.secrets} == {'unrelated'}
    assert out.config == {'foo': 'bar'}


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_raises_without_a_relation(remote: _Remote, mocked: None):
    """A missing relation is not an absence of data -- it's an incoherent call."""
    with pytest.raises(ValueError, match='needs a relation'):
        remote.publish(ops.testing.State())


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_does_not_raise_when_there_is_nothing_to_answer(remote: _Remote, mocked: None):
    """A test that arranges this relation incidentally shouldn't be obstructed."""
    remote.publish(_bare_state(remote))


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_is_idempotent(remote: _Remote, mocked: None):
    """publish recomputes, so calling it twice with nothing else changed changes nothing.

    FIXME: assert the same of any secrets or other state this remote is responsible for.
    """
    once = remote.publish(_bare_state(remote))
    twice = remote.publish(once)
    assert remote.get_relation(twice).remote_app_data == (
        remote.get_relation(once).remote_app_data
    )
    assert remote.get_relation(twice).remote_units_data == (
        remote.get_relation(once).remote_units_data
    )


@pytest.mark.skip(reason='FIXME: implement publish, then this.')
def test_publish_removes_what_is_no_longer_warranted():
    """publish recomputes rather than appends.

    FIXME: run the charm so that it withdraws something it previously published -- a config
    change is the usual way -- then publish again and assert that the answer to the
    withdrawn request is gone, while the answers still warranted remain.
    """


@pytest.mark.skip(reason='FIXME: implement publish, then this.')
def test_publish_derives_its_answer_from_what_the_charm_published():
    """The conformance test: two charms asking for different things.

    A remote that ignored the charm's relation data and wrote canned values would satisfy
    every other clause of the contract while reintroducing exactly the silent mismatches the
    package exists to prevent. This is the one property that can't be checked by reading a
    signature, so every testing package must have this test.

    FIXME: build two charms that ask for different things, integrate each against its own
    context, and assert that this remote's data differs accordingly -- not merely that it is
    non-empty. Delete this test instead if this role's remote writes *first*, since then
    there is nothing to derive from.
    """


# ----------------------------------------------------------------------- run_changed


def test_run_changed_is_equivalent_to_one_ctx_run(requirer_ctx: _Ctx, mocked: None):
    """Its equivalence to a single ctx.run for relation-changed is part of its contract."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True), end='published'
    )
    before = len(requirer_ctx.emitted_events)
    REMOTES[0].run_changed(requirer_ctx, state)
    changed = [
        event
        for event in requirer_ctx.emitted_events[before:]
        if isinstance(event, ops.RelationChangedEvent)
    ]
    assert len(changed) == 1
    assert changed[0].relation.id == REMOTES[0].get_relation(state).id
    # The remote has one unit, so the method names it rather than let ops.testing warn.
    assert changed[0].unit is not None
    assert changed[0].unit.name == f'{REMOTES[0].remote_app_name}/0'


def test_run_changed_raises_without_a_relation(requirer_ctx: _Ctx, mocked: None):
    with pytest.raises(KeyError, match='no relation'):
        REMOTES[0].run_changed(requirer_ctx, ops.testing.State())
