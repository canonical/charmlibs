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
from charmlibs.interfaces import certificate_transfer as certificate_transfer
from charmlibs.interfaces import certificate_transfer_testing as certificate_transfer_testing

if typing.TYPE_CHECKING:
    _Ctx: typing.TypeAlias = ops.testing.Context[requirer_charm.RequirerCharm]

_Remote: typing.TypeAlias = (
    certificate_transfer_testing.RemoteProvider | certificate_transfer_testing.RemoteRequirer
)

CLASSES: list[type[_Remote]] = [
    certificate_transfer_testing.RemoteProvider,
    certificate_transfer_testing.RemoteRequirer,
]
PROVIDER = certificate_transfer_testing.RemoteProvider('certificates')
REQUIRER = certificate_transfer_testing.RemoteRequirer('certificates')
REMOTES: list[_Remote] = [PROVIDER, REQUIRER]
IDS = ['RemoteProvider', 'RemoteRequirer']

ROOT = '-----BEGIN CERTIFICATE-----\nroot\n-----END CERTIFICATE-----'
INTERMEDIATE = '-----BEGIN CERTIFICATE-----\nintermediate\n-----END CERTIFICATE-----'


def _bare_state(remote: _Remote) -> ops.testing.State:
    """A bare relation for ``remote``, built from its own attributes so the two agree."""
    relation = ops.testing.Relation(
        remote.endpoint,
        interface='certificate_transfer',
        remote_app_name=remote.remote_app_name,
    )
    return ops.testing.State(leader=True, relations=[relation])


def _transferred(remote: _Remote, state: ops.testing.State) -> set[str] | None:
    """The certificates this remote has published, straight off the wire, or ``None``.

    Looks in both of the interface's wire formats, and returns ``None`` where the remote has
    written neither. Nothing else in this repository reads a databag this way; that is the
    point of the package.
    """
    relation = remote.get_relation(state)
    if 'certificates' in relation.remote_app_data:
        return set(json.loads(relation.remote_app_data['certificates']))
    unit_data = relation.remote_units_data[0]
    if 'chain' in unit_data:
        return set(json.loads(unit_data['chain']))
    return None


def _wire_version(remote: _Remote, state: ops.testing.State) -> int | None:
    """Which of the interface's two formats this remote wrote in, or ``None`` for neither."""
    relation = remote.get_relation(state)
    if 'certificates' in relation.remote_app_data:
        return 1
    if 'chain' in relation.remote_units_data[0]:
        return 0
    return None


# ----------------------------------------------------------- construction and identity


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_endpoint_is_required_and_positional(cls: type[_Remote]):
    """endpoint must be passable positionally or by keyword, and must be required."""
    assert cls('certificates').endpoint == 'certificates'
    assert cls(endpoint='certificates').endpoint == 'certificates'
    with pytest.raises(TypeError):
        cls()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_every_other_argument_is_keyword_only(cls: type[_Remote]):
    """All other arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        cls('certificates', 'remote')  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_endpoint_and_remote_app_name_are_readable(cls: type[_Remote]):
    """Both must be readable, so a hand-built bare Relation can agree with them."""
    assert cls('certificates').endpoint == 'certificates'
    assert cls('certificates').remote_app_name == 'remote'
    assert cls('certificates', remote_app_name='other').remote_app_name == 'other'


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_remotes_are_immutable(remote: _Remote):
    """The arguments given at construction cannot be changed afterwards.

    Read-only properties rather than a frozen dataclass, so the error is AttributeError.
    """
    with pytest.raises(AttributeError):
        remote.endpoint = 'other'  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        remote.remote_app_name = 'other'  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        remote.interface_version = 1  # pyright: ignore[reportAttributeAccessIssue]


def test_provider_certificates_are_immutable():
    with pytest.raises(AttributeError):
        PROVIDER.certificates = ()  # pyright: ignore[reportAttributeAccessIssue]


def test_provider_certificates_do_not_alias_the_argument():
    """A caller mutating the list it passed must not change what the remote transfers."""
    certificates = [ROOT]
    remote = certificate_transfer_testing.RemoteProvider('certificates', certificates=certificates)
    certificates.append(INTERMEDIATE)
    assert remote.certificates == (ROOT,)


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_repr_shows_the_arguments_the_caller_chose(remote: _Remote):
    """pytest derives parametrize IDs from it, so it must be short and self-describing."""
    assert repr(remote) == f"{type(remote).__name__}('certificates')"
    other = type(remote)('certificates', remote_app_name='other')
    assert repr(other) == f"{type(remote).__name__}('certificates', remote_app_name='other')"


def test_repr_shows_the_library_specific_arguments():
    """The certificates are counted rather than shown: a PEM is over a kilobyte."""
    assert repr(certificate_transfer_testing.RemoteProvider('certificates', certificates=[])) == (
        "RemoteProvider('certificates', certificates=<0>)"
    )
    assert (
        repr(
            certificate_transfer_testing.RemoteProvider(
                'certificates', certificates=[ROOT, INTERMEDIATE], interface_version=0
            )
        )
        == "RemoteProvider('certificates', certificates=<2>, interface_version=0)"
    )
    assert (
        repr(certificate_transfer_testing.RemoteRequirer('certificates', interface_version=0))
        == "RemoteRequirer('certificates', interface_version=0)"
    )


# ---------------------------------------------------------------- argument validation


@pytest.mark.parametrize('cls', CLASSES, ids=IDS)
def test_rejects_a_version_the_interface_does_not_have(cls: type[_Remote]):
    """Misuse raises early, at construction, rather than quietly writing the wrong format."""
    with pytest.raises(ValueError, match='not a version'):
        cls('certificates', interface_version=typing.cast('typing.Any', 2))


def test_requirer_rejects_no_version_at_all():
    """A requirer always has a version; v0's is spelled by writing nothing, not by None."""
    with pytest.raises(ValueError, match='not a version'):
        certificate_transfer_testing.RemoteRequirer(
            'certificates', interface_version=typing.cast('typing.Any', None)
        )


def test_provider_accepts_deciding_the_version_for_itself():
    """None is the default, and is distinct from being told to use v1."""
    assert certificate_transfer_testing.RemoteProvider('certificates').interface_version is None
    forced = certificate_transfer_testing.RemoteProvider('certificates', interface_version=1)
    assert forced.interface_version == 1


def test_provider_accepts_having_nothing_to_transfer():
    """Distinct from the default: this provider answers, and its answer is empty."""
    assert (
        certificate_transfer_testing.RemoteProvider('certificates', certificates=[]).certificates
        == ()
    )
    assert len(certificate_transfer_testing.RemoteProvider('certificates').certificates) == 1


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
    with certificate_transfer_testing.mocked(), certificate_transfer_testing.mocked():
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
    assert relation.interface == 'certificate_transfer'


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


def test_integrate_end_integrated_leaves_the_charm_having_advertised_its_version(
    requirer_ctx: _Ctx, mocked: None
):
    """The requirer's whole half of this interface is the version it understands."""
    state = PROVIDER.integrate(
        requirer_ctx,
        ops.testing.State.from_context(requirer_ctx, leader=True),
        end='integrated',
    )
    assert PROVIDER.get_relation(state).local_app_data == {'version': '1'}
    assert _transferred(PROVIDER, state) is None


def test_integrate_end_published_leaves_the_certificates_unread(requirer_ctx: _Ctx, mocked: None):
    state = PROVIDER.integrate(
        requirer_ctx,
        ops.testing.State.from_context(requirer_ctx, leader=True),
        end='published',
    )
    assert _transferred(PROVIDER, state) == set(PROVIDER.certificates)
    # The charm hasn't run against them yet, so it is still waiting.
    assert isinstance(state.unit_status, ops.testing.BlockedStatus)


def test_integrate_end_received_settles_the_relation(requirer_ctx: _Ctx, mocked: None):
    state = PROVIDER.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    assert _transferred(PROVIDER, state) == set(PROVIDER.certificates)
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
        remote.endpoint, remote_app_name='someone-else', remote_app_data={'version': '1'}
    )
    state = _bare_state(remote)
    state = dataclasses.replace(state, relations=[*state.relations, theirs])
    out = remote.publish(state)
    untouched = next(r for r in out.relations if r.id == theirs.id)
    assert isinstance(untouched, ops.testing.Relation)
    assert untouched.remote_app_data == {'version': '1'}


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_raises_without_a_relation(remote: _Remote, mocked: None):
    """A missing relation is not an absence of data -- it's an incoherent call."""
    with pytest.raises(ValueError, match='needs a relation'):
        remote.publish(ops.testing.State())


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_does_not_raise_on_a_relation_the_charm_has_not_run_against(
    remote: _Remote, mocked: None
):
    """A test that arranges this relation incidentally shouldn't be obstructed."""
    remote.publish(_bare_state(remote))


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_keeps_jujus_own_keys_in_the_unit_databag(remote: _Remote, mocked: None):
    """ops.testing puts the network keys there; only the interface's keys are the remote's."""
    state = remote.publish(_bare_state(remote))
    assert 'ingress-address' in remote.get_relation(state).remote_units_data[0]


@pytest.mark.parametrize('remote', REMOTES, ids=IDS)
def test_publish_is_idempotent(remote: _Remote, mocked: None):
    """publish recomputes, so calling it twice with nothing else changed changes nothing."""
    once = remote.publish(_bare_state(remote))
    twice = remote.publish(once)
    assert twice == once


def test_provider_publish_writes_v0_when_the_charm_has_not_advertised_a_version(mocked: None):
    """Which is what the real provider library does, and is how v0 requirers still work."""
    state = PROVIDER.publish(_bare_state(PROVIDER))
    assert _wire_version(PROVIDER, state) == 0
    assert _transferred(PROVIDER, state) == set(PROVIDER.certificates)


def test_provider_publish_writes_nothing_for_v0_with_no_certificates(mocked: None):
    """v0 has no way to say "none": ``ca`` and ``certificate`` are single required strings."""
    remote = certificate_transfer_testing.RemoteProvider('certificates', certificates=[])
    state = _bare_state(remote)
    assert remote.publish(state) == state


def test_provider_publish_writes_an_empty_set_for_v1_with_no_certificates(
    requirer_ctx: _Ctx, mocked: None
):
    """Not the same as having nothing to say -- this is an answer, and it is empty."""
    remote = certificate_transfer_testing.RemoteProvider('certificates', certificates=[])
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    assert _transferred(remote, state) == set()


def test_provider_publish_switching_format_clears_the_other_one(mocked: None):
    """The state must never hold both halves of the conversation at once."""
    as_v0 = certificate_transfer_testing.RemoteProvider('certificates', interface_version=0)
    as_v1 = certificate_transfer_testing.RemoteProvider('certificates', interface_version=1)
    state = as_v0.publish(_bare_state(as_v0))
    assert _wire_version(as_v0, state) == 0
    state = as_v1.publish(state)
    assert _wire_version(as_v1, state) == 1
    assert 'chain' not in as_v1.get_relation(state).remote_units_data[0]
    state = as_v0.publish(state)
    assert _wire_version(as_v0, state) == 0
    assert as_v0.get_relation(state).remote_app_data == {}


def test_provider_publish_removes_what_is_no_longer_warranted(requirer_ctx: _Ctx, mocked: None):
    """publish recomputes rather than appends: a rotated-out CA goes away."""
    remote = certificate_transfer_testing.RemoteProvider(
        'certificates', certificates=[ROOT, INTERMEDIATE]
    )
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx, leader=True)
    )
    assert _transferred(remote, state) == {ROOT, INTERMEDIATE}
    rotated = certificate_transfer_testing.RemoteProvider('certificates', certificates=[ROOT])
    assert _transferred(rotated, rotated.publish(state)) == {ROOT}


def test_provider_publish_writes_the_certificates_in_a_stable_order(mocked: None):
    """The interface carries a set, so only sorting keeps the bytes the same run to run."""
    remote = certificate_transfer_testing.RemoteProvider(
        'certificates', certificates=[INTERMEDIATE, ROOT], interface_version=1
    )
    state = remote.publish(_bare_state(remote))
    written = remote.get_relation(state).remote_app_data['certificates']
    assert written == json.dumps(sorted([ROOT, INTERMEDIATE]))


def test_requirer_publish_advertises_its_version(mocked: None):
    """The requirer speaks first, so it always writes: there is nothing to wait for."""
    assert REQUIRER.interface_version == 1
    state = REQUIRER.publish(_bare_state(REQUIRER))
    assert REQUIRER.get_relation(state).remote_app_data == {'version': '1'}


def test_requirer_publish_writes_nothing_for_v0(mocked: None):
    """An absent version key *is* how v0 is spelled -- a remote that would not write."""
    remote = certificate_transfer_testing.RemoteRequirer('certificates', interface_version=0)
    state = _bare_state(remote)
    assert remote.publish(state) == state


def test_requirer_publish_removes_what_is_no_longer_warranted(mocked: None):
    """A remote that has become a v0 one clears the key rather than leaving it behind."""
    state = REQUIRER.publish(_bare_state(REQUIRER))
    older = certificate_transfer_testing.RemoteRequirer('certificates', interface_version=0)
    assert older.get_relation(older.publish(state)).remote_app_data == {}


def test_requirer_publish_leaves_the_unit_databag_alone(mocked: None):
    """``certificate_transfer`` requirers write to the application databag only."""
    state = REQUIRER.publish(_bare_state(REQUIRER))
    for databag in REQUIRER.get_relation(state).remote_units_data.values():
        assert not {'version', 'certificates', 'ca', 'certificate', 'chain'} & set(databag)


def test_publish_derives_its_answer_from_what_the_charm_published(mocked: None):
    """The conformance test OP093 requires: two charms saying different things.

    What a ``certificate_transfer`` requirer says is which version of the wire format it
    understands, so that is what the provider's answer must be derived from -- and it is
    what the real ``CertificateTransferProvides`` derives it from too. A remote that ignored
    the charm's relation data and always wrote one format would satisfy every other clause
    of the contract while handing a v0 charm data it cannot read.

    There is no counterpart for ``RemoteRequirer``: the requirer writes first on this
    interface, so it has nothing to derive from.
    """
    remote = certificate_transfer_testing.RemoteProvider('certificates')
    charms = {
        # A modern requirer: the library advertises version 1 on relation-created.
        1: requirer_charm.RequirerCharm,
        # A requirer from before v1 of the interface, which advertises nothing.
        0: _v0_requirer_charm(),
    }
    answers: dict[int, int | None] = {}
    for expected, charm_type in charms.items():
        ctx = ops.testing.Context(charm_type, meta=requirer_charm.META)
        state = remote.integrate(ctx, ops.testing.State.from_context(ctx, leader=True))
        answers[expected] = _wire_version(remote, state)
        # Whichever format it chose, the certificates themselves got through.
        assert _transferred(remote, state) == set(remote.certificates)
    assert answers == {1: 1, 0: 0}


def _v0_requirer_charm() -> type[ops.CharmBase]:
    """A requirer charm as it was before v1 of the interface: it advertises no version.

    Written out rather than assembled from the library, because the library has no v0
    requirer left in it -- advertising nothing is precisely what it stopped doing.
    """

    class _Charm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            framework.observe(self.on['certificates'].relation_changed, self._noop)

        def _noop(self, _: ops.EventBase) -> None:
            pass

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
