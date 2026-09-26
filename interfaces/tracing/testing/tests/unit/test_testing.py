# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the remote classes' own contract.

These read relation data directly, which a charm test should never do -- the point of the
package is that charm tests don't have to. Here it is the subject.
"""

from __future__ import annotations

import dataclasses
import json
import typing

import ops
import ops.testing
import pytest

import requirer_charm

# The aliased form keeps these on separate lines, which a namespace package split across
# two distributions needs for pyright to resolve both halves.
from charmlibs.interfaces import tracing as tracing
from charmlibs.interfaces import tracing_testing as tracing_testing

if typing.TYPE_CHECKING:
    _Ctx: typing.TypeAlias = ops.testing.Context[requirer_charm.RequirerCharm]

_Remote: typing.TypeAlias = tracing_testing.RemoteProvider | tracing_testing.RemoteRequirer

CLASSES: list[type[_Remote]] = [
    tracing_testing.RemoteProvider,
    tracing_testing.RemoteRequirer,
]
PROVIDER = tracing_testing.RemoteProvider('tracing')
REQUIRER = tracing_testing.RemoteRequirer('tracing')
REMOTES: list[_Remote] = [PROVIDER, REQUIRER]
IDS = ['RemoteProvider', 'RemoteRequirer']


def _bare_state(remote: _Remote) -> ops.testing.State:
    """A bare relation for ``remote``, built from its own attributes so the two agree."""
    relation = ops.testing.Relation(
        remote.endpoint, interface='tracing', remote_app_name=remote.remote_app_name
    )
    return ops.testing.State(leader=True, relations=[relation])


def _wire(databag: typing.Mapping[str, str]) -> typing.Any:
    """The ``receivers`` value a databag carries, or ``None`` if it carries none."""
    raw = databag.get('receivers')
    return None if raw is None else json.loads(raw)


def _answered(remote: _Remote, state: ops.testing.State) -> typing.Any:
    """What this remote has published, straight off the wire."""
    return _wire(remote.get_relation(state).remote_app_data)


def _asked(remote: _Remote, state: ops.testing.State) -> typing.Any:
    """What the charm under test has published, straight off the wire."""
    return _wire(remote.get_relation(state).local_app_data)


def _protocol_names(receivers: typing.Any) -> list[str]:
    """The protocol names in a provider's published receiver list."""
    return [receiver['protocol']['name'] for receiver in receivers]


# ----------------------------------------------------------- construction and identity


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_endpoint_is_required_and_positional(cls: type[_Remote]):
    """endpoint must be passable positionally or by keyword, and must be required."""
    assert cls('tracing').endpoint == 'tracing'
    assert cls(endpoint='tracing').endpoint == 'tracing'
    with pytest.raises(TypeError):
        cls()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_every_other_argument_is_keyword_only(cls: type[_Remote]):
    """All other arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        cls('tracing', 'remote')  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_endpoint_and_remote_app_name_are_readable(cls: type[_Remote]):
    """Both must be readable, so a hand-built bare Relation can agree with them."""
    assert cls('tracing').endpoint == 'tracing'
    assert cls('tracing').remote_app_name == 'remote'
    assert cls('tracing', remote_app_name='other').remote_app_name == 'other'


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_remotes_are_immutable(remote: _Remote):
    """The arguments given at construction cannot be changed afterwards.

    Read-only properties rather than a frozen dataclass, so the error is AttributeError.
    """
    with pytest.raises(AttributeError):
        remote.endpoint = 'other'  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        remote.remote_app_name = 'other'  # pyright: ignore[reportAttributeAccessIssue]


def test_provider_arguments_are_immutable():
    provider = tracing_testing.RemoteProvider('tracing')
    for name in ('supported_protocols', 'host', 'tls'):
        with pytest.raises(AttributeError):
            setattr(provider, name, None)


def test_requirer_arguments_are_immutable():
    with pytest.raises(AttributeError):
        tracing_testing.RemoteRequirer('tracing').protocols = ()  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_repr_shows_the_arguments_the_caller_chose(remote: _Remote):
    """pytest derives parametrize IDs from it, so it must be short and self-describing."""
    assert repr(remote) == f"{type(remote).__name__}('tracing')"
    other = type(remote)('tracing', remote_app_name='other')
    assert repr(other) == f"{type(remote).__name__}('tracing', remote_app_name='other')"


def test_repr_shows_the_library_specific_arguments():
    assert repr(tracing_testing.RemoteProvider('tracing', tls=True)) == (
        "RemoteProvider('tracing', tls=True)"
    )
    assert repr(tracing_testing.RemoteProvider('tracing', supported_protocols=[])) == (
        "RemoteProvider('tracing', supported_protocols=())"
    )
    assert repr(tracing_testing.RemoteRequirer('tracing', protocols=['zipkin'])) == (
        "RemoteRequirer('tracing', protocols=('zipkin',))"
    )


# ---------------------------------------------------------------- argument validation


def test_provider_rejects_a_protocol_the_interface_does_not_define():
    """Misuse raises early, at construction, rather than quietly answering nothing."""
    with pytest.raises(ValueError, match='does not define'):
        tracing_testing.RemoteProvider(
            'tracing',
            supported_protocols=['otlp_http', typing.cast('typing.Any', 'smoke_signals')],
        )


def test_requirer_rejects_a_protocol_the_interface_does_not_define():
    with pytest.raises(ValueError, match='does not define'):
        tracing_testing.RemoteRequirer(
            'tracing', protocols=[typing.cast('typing.Any', 'smoke_signals')]
        )


def test_requirer_rejects_an_empty_request():
    """``request_protocols`` rejects one too -- a requirer that wants nothing doesn't write."""
    with pytest.raises(ValueError, match='at least one protocol'):
        tracing_testing.RemoteRequirer('tracing', protocols=[])


def test_provider_accepts_supporting_nothing():
    """Distinct from the default: this provider answers, and its answer is empty."""
    assert (
        tracing_testing.RemoteProvider('tracing', supported_protocols=[]).supported_protocols == ()
    )
    assert tracing_testing.RemoteProvider('tracing').supported_protocols is None


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
    with tracing_testing.mocked(), tracing_testing.mocked():
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


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_get_relation_raises_when_two_relations_match(remote: _Remote):
    """Silently picking one would let a test assert against the wrong application."""
    relations = [
        ops.testing.Relation(remote.endpoint, remote_app_name=remote.remote_app_name)
        for _ in range(2)
    ]
    with pytest.raises(ValueError, match='matches 2 relations'):
        remote.get_relation(ops.testing.State(relations=relations))


# ------------------------------------------------------------------------- integrate


def test_integrate_adds_the_relation(requirer_ctx: _Ctx, mocked: None):
    state = PROVIDER.integrate(requirer_ctx, ops.testing.State(leader=True))
    relation = PROVIDER.get_relation(state)
    assert relation.endpoint == PROVIDER.endpoint
    assert relation.remote_app_name == PROVIDER.remote_app_name
    assert relation.interface == 'tracing'


def test_integrate_adopts_a_bare_relation(requirer_ctx: _Ctx, mocked: None):
    """ops.testing.State.from_context puts one there for every endpoint in the metadata."""
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True)
    state_out = PROVIDER.integrate(requirer_ctx, state_in)
    assert len(state_out.relations) == len(state_in.relations)


def test_integrate_rejects_an_invalid_end(requirer_ctx: _Ctx, mocked: None):
    with pytest.raises(ValueError, match='end must be'):
        PROVIDER.integrate(
            requirer_ctx, ops.testing.State(), end=typing.cast('typing.Any', 'settled')
        )


def test_integrate_rejects_a_relation_the_conversation_has_begun_on(
    requirer_ctx: _Ctx, mocked: None
):
    """integrate() starts a conversation; publish() and run_changed() carry one on."""
    state = PROVIDER.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    with pytest.raises(ValueError, match='already begun'):
        PROVIDER.integrate(requirer_ctx, state)


def test_integrate_end_integrated_leaves_the_charm_having_asked(requirer_ctx: _Ctx, mocked: None):
    state = PROVIDER.integrate(
        requirer_ctx,
        ops.testing.State.from_context(requirer_ctx, leader=True),
        end='integrated',
    )
    assert _asked(PROVIDER, state) == requirer_charm.PROTOCOLS
    assert _answered(PROVIDER, state) is None


def test_integrate_end_published_leaves_the_answer_unread(requirer_ctx: _Ctx, mocked: None):
    state = PROVIDER.integrate(
        requirer_ctx,
        ops.testing.State.from_context(requirer_ctx, leader=True),
        end='published',
    )
    assert _protocol_names(_answered(PROVIDER, state)) == requirer_charm.PROTOCOLS
    # The charm hasn't run against the answer yet, so it is still blocked on it.
    assert isinstance(state.unit_status, ops.testing.BlockedStatus)


def test_integrate_end_received_settles_the_relation(requirer_ctx: _Ctx, mocked: None):
    state = PROVIDER.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    assert _protocol_names(_answered(PROVIDER, state)) == requirer_charm.PROTOCOLS
    assert isinstance(state.unit_status, ops.testing.ActiveStatus)


def test_integrate_preserves_the_rest_of_the_state(requirer_ctx: _Ctx, mocked: None):
    """Everything the remote isn't responsible for is left as it is.

    Other *relations* are covered by the publish test below rather than here, because
    integrate runs the charm and so every endpoint in the state has to be declared in the
    charm's metadata.
    """
    secret = ops.testing.Secret({'a': 'b'}, label='unrelated', owner='unit')
    state_in = ops.testing.State.from_context(requirer_ctx, leader=True, secrets=[secret])
    state_out = PROVIDER.integrate(requirer_ctx, state_in)
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
def test_publish_preserves_other_remotes_on_the_same_endpoint(remote: _Remote, mocked: None):
    """State belonging to another simulated application must be left alone."""
    theirs = ops.testing.Relation(
        remote.endpoint, remote_app_name='someone-else', remote_app_data={'receivers': '[]'}
    )
    state = _bare_state(remote)
    state = dataclasses.replace(state, relations=[*state.relations, theirs])
    out = remote.publish(state)
    untouched = next(r for r in out.relations if r.id == theirs.id)
    assert isinstance(untouched, ops.testing.Relation)
    assert untouched.remote_app_data == {'receivers': '[]'}


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_raises_without_a_relation(remote: _Remote, mocked: None):
    """A missing relation is not an absence of data -- it's an incoherent call."""
    with pytest.raises(ValueError, match='needs a relation'):
        remote.publish(ops.testing.State())


def test_provider_publish_does_nothing_when_there_is_nothing_to_answer(mocked: None):
    """A test that arranges this relation incidentally shouldn't be obstructed."""
    state = _bare_state(PROVIDER)
    assert PROVIDER.publish(state) == state


def test_provider_publish_answers_emptily_when_it_supports_none_of_what_was_asked(
    requirer_ctx: _Ctx, mocked: None
):
    """Not the same as having nothing to answer -- this is an answer, and it is empty.

    A requirer can tell the two apart: ``is_ready`` is false where nothing was published,
    and true where an empty receiver list was.
    """
    remote = tracing_testing.RemoteProvider('tracing', supported_protocols=[])
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    assert _answered(remote, state) == []


def test_requirer_publish_writes_its_request(mocked: None):
    """The requirer speaks first, so it always writes: there is nothing to wait for."""
    state = REQUIRER.publish(_bare_state(REQUIRER))
    assert _answered(REQUIRER, state) == list(REQUIRER.protocols)


def test_requirer_publish_leaves_the_unit_databag_alone(mocked: None):
    """``tracing`` requirers write to the application databag only."""
    state = REQUIRER.publish(_bare_state(REQUIRER))
    for databag in REQUIRER.get_relation(state).remote_units_data.values():
        assert 'receivers' not in databag


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_is_idempotent(remote: _Remote, mocked: None):
    """publish recomputes, so calling it twice with nothing else changed changes nothing."""
    once = remote.publish(_bare_state(remote))
    twice = remote.publish(once)
    assert twice == once


def test_provider_publish_removes_what_is_no_longer_warranted(requirer_ctx: _Ctx, mocked: None):
    """publish recomputes rather than appends.

    The charm withdraws one of its two requests -- edited onto the wire here, because no
    charm in this repository changes its mind -- and the receiver answering it goes away
    while the one still warranted stays.
    """
    state = PROVIDER.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    assert _protocol_names(_answered(PROVIDER, state)) == ['otlp_http', 'zipkin']
    relation = PROVIDER.get_relation(state)
    withdrawn = dataclasses.replace(relation, local_app_data={'receivers': '["otlp_http"]'})
    state = dataclasses.replace(
        state, relations={r for r in state.relations if r.id != relation.id} | {withdrawn}
    )
    state = PROVIDER.publish(state)
    assert _protocol_names(_answered(PROVIDER, state)) == ['otlp_http']


def test_requirer_publish_removes_what_is_no_longer_warranted(mocked: None):
    """A remote asking for less writes less, rather than adding to what is there."""
    state = REQUIRER.publish(_bare_state(REQUIRER))
    narrower = tracing_testing.RemoteRequirer('tracing', protocols=['zipkin'])
    assert _answered(narrower, narrower.publish(state)) == ['zipkin']


def test_publish_derives_its_answer_from_what_the_charm_published(mocked: None):
    """The conformance test OP093 requires: two charms asking for different things.

    A remote that ignored the charm's relation data and wrote canned values would satisfy
    every other clause of the contract while reintroducing exactly the silent mismatches the
    package exists to prevent. This is the one property that can't be checked by reading a
    signature.

    There is no counterpart for ``RemoteRequirer``: the requirer writes first on this
    interface, so it has nothing to derive from.
    """
    remote = tracing_testing.RemoteProvider('tracing')
    requests: list[list[tracing.ReceiverProtocol]] = [['otlp_http'], ['zipkin', 'jaeger_grpc']]
    answers: list[list[str]] = []
    for protocols in requests:
        ctx = ops.testing.Context(_requirer_charm_requesting(protocols), meta=requirer_charm.META)
        state = remote.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
        answers.append(_protocol_names(_answered(remote, state)))
    assert answers == [['otlp_http'], ['zipkin', 'jaeger_grpc']]


def _requirer_charm_requesting(
    protocols: list[tracing.ReceiverProtocol],
) -> type[ops.CharmBase]:
    """A requirer charm that asks for exactly ``protocols`` and does nothing else."""

    class _Charm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.tracing = tracing.TracingEndpointRequirer(self, protocols=protocols)

    return _Charm


# ----------------------------------------------------------------------- run_changed


def test_run_changed_is_equivalent_to_one_ctx_run(requirer_ctx: _Ctx, mocked: None):
    """Its equivalence to a single ctx.run for relation-changed is part of its contract."""
    state = PROVIDER.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True), end='published'
    )
    before = len(requirer_ctx.emitted_events)
    PROVIDER.run_changed(requirer_ctx, state)
    changed = [
        event
        for event in requirer_ctx.emitted_events[before:]
        if isinstance(event, ops.RelationChangedEvent)
    ]
    assert len(changed) == 1
    assert changed[0].relation.id == PROVIDER.get_relation(state).id
    # The remote has one unit, so the method names it rather than let ops.testing warn.
    assert changed[0].unit is not None
    assert changed[0].unit.name == f'{PROVIDER.remote_app_name}/0'


def test_run_changed_raises_without_a_relation(requirer_ctx: _Ctx, mocked: None):
    with pytest.raises(KeyError, match='no relation'):
        PROVIDER.run_changed(requirer_ctx, ops.testing.State())
