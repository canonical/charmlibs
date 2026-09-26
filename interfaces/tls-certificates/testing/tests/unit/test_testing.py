# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the remote classes' own contract, as OP093 specifies it.

These read relation data directly, which a charm test should never do -- the point of the
package is that charm tests don't have to. Here it is the subject.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import typing

import ops
import ops.testing
import pytest

import requirer_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

JUJU_NETWORK_KEYS = {"egress-subnets", "ingress-address", "private-address"}
REMOTES = [
    tls_certificates_testing.RemoteProvider("certificates"),
    tls_certificates_testing.RemoteRequirer("certificates"),
]
IDS = ["RemoteProvider", "RemoteRequirer"]

_Remote: typing.TypeAlias = (
    "tls_certificates_testing.RemoteProvider | tls_certificates_testing.RemoteRequirer"
)
_Scope: typing.TypeAlias = "typing.Literal[tls_certificates.Mode.APP, tls_certificates.Mode.UNIT]"


# ---------------------------------------------------------------- construction & identity


@pytest.mark.parametrize(
    "cls",
    [
        tls_certificates_testing.RemoteProvider,
        tls_certificates_testing.RemoteRequirer,
    ],
    ids=IDS,
)
def test_endpoint_is_required_and_positional(cls: type[_Remote]):
    """OP093: endpoint must be passable positionally or by keyword, and must be required."""
    assert cls("certificates").endpoint == "certificates"
    assert cls(endpoint="certificates").endpoint == "certificates"
    with pytest.raises(TypeError):
        cls()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize(
    "cls",
    [
        tls_certificates_testing.RemoteProvider,
        tls_certificates_testing.RemoteRequirer,
    ],
    ids=IDS,
)
def test_every_other_argument_is_keyword_only(cls: type[_Remote]):
    """OP093: all other arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        cls("certificates", "remote")  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize(
    "cls",
    [
        tls_certificates_testing.RemoteProvider,
        tls_certificates_testing.RemoteRequirer,
    ],
    ids=IDS,
)
def test_endpoint_and_remote_app_name_are_readable(cls: type[_Remote]):
    """OP093: both must be readable, so a hand-built bare Relation can agree with them."""
    assert cls("certificates").endpoint == "certificates"
    assert cls("certificates").remote_app_name == "remote"
    assert cls("certificates", remote_app_name="ca").remote_app_name == "ca"


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_remotes_are_immutable(remote: _Remote):
    """OP093: the arguments given at construction cannot be changed afterwards.

    Read-only properties rather than a frozen dataclass, so the error is AttributeError.
    """
    with pytest.raises(AttributeError):
        remote.endpoint = "other"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        remote.remote_app_name = "other"  # pyright: ignore[reportAttributeAccessIssue]


def test_provider_arguments_are_immutable():
    remote = tls_certificates_testing.RemoteProvider("certificates")
    for name in ("outcome", "capabilities", "validity"):
        with pytest.raises(AttributeError):
            setattr(remote, name, None)


def test_requirer_arguments_are_immutable():
    remote = tls_certificates_testing.RemoteRequirer("certificates")
    for name in ("certificate_requests", "mode", "certificate_requests_by_mode", "private_key"):
        with pytest.raises(AttributeError):
            setattr(remote, name, None)


@pytest.mark.parametrize(
    "cls",
    [
        tls_certificates_testing.RemoteProvider,
        tls_certificates_testing.RemoteRequirer,
    ],
    ids=IDS,
)
def test_remotes_are_not_dataclasses(cls: type[_Remote]):
    """Plain classes, deliberately.

    A dataclass would satisfy every property OP093 asks for, but it commits the package to
    `replace`, `astuple`, `asdict`, `is_dataclass` and `__dataclass_fields__` as public API
    -- which makes adding an optional argument, or reordering the existing ones, a breaking
    change. See "Don't use dataclasses in your library's public API" on the Charmhub forum.
    """
    assert not dataclasses.is_dataclass(cls)


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_remotes_have_a_useful_repr(remote: _Remote):
    """OP093: pytest derives parametrize IDs from it, and it locates errors."""
    text = repr(remote)
    assert type(remote).__name__ in text
    assert "certificates" in text


def test_repr_omits_arguments_left_at_default():
    """Short enough to read in a parametrize ID, and it shows what the caller chose."""
    assert repr(tls_certificates_testing.RemoteProvider("certificates")) == (
        "RemoteProvider('certificates')"
    )
    assert repr(tls_certificates_testing.RemoteRequirer("certificates")) == (
        "RemoteRequirer('certificates')"
    )


def test_repr_shows_the_arguments_the_caller_gave():
    text = repr(
        tls_certificates_testing.RemoteProvider(
            "certificates",
            remote_app_name="ca",
            outcome=tls_certificates_testing.Outcome.denied(
                code=tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
            ),
        )
    )
    assert text == (
        "RemoteProvider('certificates', remote_app_name='ca', "
        "outcome=Outcome.denied(code=CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED))"
    )
    text = repr(
        tls_certificates_testing.RemoteRequirer("certificates", mode=tls_certificates.Mode.APP)
    )
    assert text == "RemoteRequirer('certificates', mode=Mode.APP)"


def test_repr_does_not_print_key_material():
    """A PEM key is unreadable in a parametrize ID, and printing one is a bad habit."""
    key = tls_certificates.PrivateKey.generate()
    text = repr(tls_certificates_testing.RemoteRequirer("certificates", private_key=key))
    assert "private_key=<custom>" in text
    assert "PRIVATE KEY" not in text


def test_repr_covers_every_argument():
    """Every argument a caller can give must be visible, so a failure names the right remote."""
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    provider = tls_certificates_testing.RemoteProvider(
        "certificates",
        outcome=lambda _: tls_certificates_testing.Outcome.issued(),
        capabilities=tls_certificates.ProviderCapabilities(provider_type="acme"),
        validity=datetime.timedelta(days=7),
    )
    text = repr(provider)
    for expected in ("outcome=", "capabilities=", "validity="):
        assert expected in text
    requirer = tls_certificates_testing.RemoteRequirer(
        "certificates",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={tls_certificates.Mode.APP: [request]},
    )
    text = repr(requirer)
    assert "mode=Mode.APP_AND_UNIT" in text
    assert "certificate_requests_by_mode={'Mode.APP':" in text
    text = repr(
        tls_certificates_testing.RemoteRequirer("certificates", certificate_requests=[request])
    )
    assert "certificate_requests=[" in text


def test_the_arguments_are_readable_as_attributes():
    """Not required by OP093 beyond endpoint and remote_app_name, but cheap and expected.

    Read-only, and normalised: the requests come back as tuples whatever iterable went in, so
    a remote can't be emptied by being used once.
    """
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    key = tls_certificates.PrivateKey.generate()
    provider = tls_certificates_testing.RemoteProvider(
        "certificates",
        outcome=tls_certificates_testing.Outcome.revoked(),
        capabilities=tls_certificates.ProviderCapabilities(provider_type="acme"),
        validity=datetime.timedelta(days=7),
    )
    assert provider.outcome is tls_certificates_testing.Outcome.revoked()
    assert provider.capabilities is not None
    assert provider.capabilities.provider_type == "acme"
    assert provider.validity == datetime.timedelta(days=7)
    requirer = tls_certificates_testing.RemoteRequirer(
        "certificates", certificate_requests=iter([request]), private_key=key
    )
    assert requirer.certificate_requests == (request,)
    assert requirer.mode is tls_certificates.Mode.UNIT
    assert requirer.certificate_requests_by_mode is None
    assert requirer.private_key == key
    by_mode = tls_certificates_testing.RemoteRequirer(
        "certificates",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={tls_certificates.Mode.APP: iter([request])},
    )
    assert by_mode.certificate_requests_by_mode == {tls_certificates.Mode.APP: (request,)}


# ---------------------------------------------------------------------- get_relation


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_get_relation_raises_without_a_relation(remote: _Remote):
    """ops.testing.State raises KeyError for a missing relation, so this does too."""
    with pytest.raises(KeyError, match="no relation"):
        remote.get_relation(ops.testing.State())


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_get_relation_matches_on_endpoint_and_app_name(remote: _Remote):
    """A remote is identified by both, so that one endpoint can carry several."""
    mine = ops.testing.Relation("certificates", remote_app_name="remote")
    theirs = ops.testing.Relation("certificates", remote_app_name="other")
    elsewhere = ops.testing.Relation("other-endpoint", remote_app_name="remote")
    state = ops.testing.State(relations=[mine, theirs, elsewhere])
    assert remote.get_relation(state).id == mine.id


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_get_relation_raises_on_an_ambiguous_state(remote: _Remote):
    """Two relations for one remote can't be disambiguated, so don't guess."""
    state = ops.testing.State(
        relations=[
            ops.testing.Relation("certificates", remote_app_name="remote"),
            ops.testing.Relation("certificates", remote_app_name="remote"),
        ]
    )
    with pytest.raises(ValueError, match="matches 2 relations"):
        remote.get_relation(state)


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_a_hand_built_bare_relation_agrees_with_the_remote(remote: _Remote):
    """The reason endpoint and remote_app_name are readable.

    A relation with nothing written at all is below `end="integrated"`, so it is built by
    hand -- and the remote that will later operate on it has to find it.
    """
    remote = type(remote)(remote.endpoint, remote_app_name="ca")
    relation = ops.testing.Relation(
        remote.endpoint, interface="tls-certificates", remote_app_name=remote.remote_app_name
    )
    state = ops.testing.State(relations=[relation])
    assert remote.get_relation(state).id == relation.id


# --------------------------------------------------------------------- publish contract


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_publish_raises_without_a_relation(remote: _Remote, mocked: None):
    """A missing relation isn't an absence of data -- it's an incoherent call."""
    with pytest.raises(ValueError, match="needs a relation"):
        remote.publish(ops.testing.State())


def test_publish_does_not_raise_on_an_absence_of_data(mocked: None):
    """OP093: where there's nothing to answer, publish writes nothing and returns the state.

    A test that arranges this relation incidentally, while being about something else,
    mustn't be obstructed.
    """
    relation = ops.testing.Relation("certificates", interface="tls-certificates")
    state = ops.testing.State(relations=[relation])
    out = REMOTES[0].publish(state)
    assert not _interface_keys(_relation(out, relation.id).remote_app_data)


def test_publish_warns_when_a_non_leader_explains_the_silence(
    mocked: None, caplog: pytest.LogCaptureFixture
):
    """A specific, likely reason for an empty relation is worth saying out loud.

    Not raised: a Mode.UNIT requirer publishes as a non-leader perfectly well, so
    non-leadership is a likely explanation rather than a certain one.
    """
    relation = ops.testing.Relation("certificates", interface="tls-certificates")
    state = ops.testing.State(relations=[relation], leader=False)
    REMOTES[0].publish(state)
    assert "not the leader" in caplog.text


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_publish_preserves_the_rest_of_the_state(remote: _Remote, mocked: None):
    """OP093: other relations, endpoints, containers and config are preserved as-is."""
    mine = ops.testing.Relation("certificates", interface="tls-certificates")
    other = ops.testing.Relation("other-endpoint", remote_app_data={"key": "value"})
    secret = ops.testing.Secret({"a": "b"}, label="unrelated", owner="unit")
    state = ops.testing.State(
        relations=[mine, other], secrets=[secret], leader=True, config={"foo": "bar"}
    )
    out = remote.publish(state)
    assert _relation(out, other.id).remote_app_data == {"key": "value"}
    assert {s.label for s in out.secrets} == {"unrelated"}
    assert out.config == {"foo": "bar"}
    assert out.leader is True


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_publish_preserves_other_remotes_on_the_same_endpoint(remote: _Remote, mocked: None):
    """OP093: state belonging to other remotes on the same endpoint must be preserved."""
    mine = ops.testing.Relation("certificates", remote_app_name="remote")
    theirs = ops.testing.Relation(
        "certificates", remote_app_name="other", remote_app_data={"certificates": "[]"}
    )
    state = ops.testing.State(relations=[mine, theirs], leader=True)
    out = remote.publish(state)
    assert _relation(out, theirs.id).remote_app_data == {"certificates": "[]"}


@pytest.mark.parametrize("remote", REMOTES, ids=IDS)
def test_publish_returns_a_copy(remote: _Remote, mocked: None):
    """OP093: each state-producing method returns a copy of the state it was given."""
    state = ops.testing.State(
        relations=[ops.testing.Relation("certificates", interface="tls-certificates")]
    )
    out = remote.publish(state)
    assert out is not state


# -------------------------------------------------------------------- integrate contract


def test_integrate_rejects_an_unknown_end(requirer_ctx: _Ctx, mocked: None):
    with pytest.raises(ValueError, match="end must be"):
        REMOTES[0].integrate(
            requirer_ctx,
            ops.testing.State.from_context(requirer_ctx),
            end="settled",  # pyright: ignore[reportArgumentType]
        )


def test_integrate_adopts_a_bare_relation(requirer_ctx: _Ctx, mocked: None):
    """State.from_context puts one there for every endpoint, so this is the common path."""
    state = ops.testing.State.from_context(requirer_ctx)
    relation = REMOTES[0].get_relation(state)
    out = REMOTES[0].integrate(requirer_ctx, state)
    assert len(out.get_relations("certificates")) == 1
    assert REMOTES[0].get_relation(out).id == relation.id


def test_integrate_creates_the_relation_when_there_is_none(requirer_ctx: _Ctx, mocked: None):
    out = REMOTES[0].integrate(requirer_ctx, ops.testing.State())
    relation = REMOTES[0].get_relation(out)
    assert relation.interface == "tls-certificates"
    assert relation.remote_app_name == "remote"


def test_integrate_raises_when_the_conversation_has_already_begun(
    requirer_ctx: _Ctx, mocked: None
):
    """integrate() starts a conversation; publish() and run_changed() carry one on."""
    state = REMOTES[0].integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with pytest.raises(ValueError, match="already begun"):
        REMOTES[0].integrate(requirer_ctx, state)


def test_integrate_fires_the_events_juju_fires(requirer_ctx: _Ctx, mocked: None):
    """relation-created, then relation-joined and relation-changed for unit 0."""
    REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="integrated"
    )
    names = [
        e.handle.kind for e in requirer_ctx.emitted_events if isinstance(e, ops.RelationEvent)
    ]
    assert names == [
        "certificates_relation_created",
        "certificates_relation_joined",
        "certificates_relation_changed",
    ]
    joined = next(e for e in requirer_ctx.emitted_events if isinstance(e, ops.RelationJoinedEvent))
    assert joined.unit is not None
    assert joined.unit.name == "remote/0"


def test_integrate_end_integrated_leaves_the_charms_side_only(requirer_ctx: _Ctx, mocked: None):
    """The charm has asked; nobody has answered."""
    out = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="integrated"
    )
    relation = REMOTES[0].get_relation(out)
    assert "certificate_signing_requests" in relation.local_unit_data
    assert not _interface_keys(relation.remote_app_data)


def test_integrate_end_published_adds_the_remotes_data(requirer_ctx: _Ctx, mocked: None):
    """The answer is on the wire, but the charm hasn't reconciled against it."""
    out = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    relation = REMOTES[0].get_relation(out)
    assert "certificates" in relation.remote_app_data
    # The charm stores each assigned certificate in a secret as it reconciles, so the
    # absence of certificate secrets is how "hasn't reconciled yet" shows up in the state.
    # (Its private key secret is there -- it created that in order to ask.)
    assert not _certificate_secrets(out)


def test_integrate_end_published_is_below_received(requirer_ctx: _Ctx, mocked: None):
    """Companion to the above, so its assertion can't be passing vacuously."""
    out = REMOTES[0].integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    assert len(_certificate_secrets(out)) == len(requirer_charm.REQUESTS)


def test_integrate_end_received_settles_the_relation(requirer_ctx: _Ctx, mocked: None):
    """The default: the charm has reconciled against the answer."""
    out = REMOTES[0].integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    assert "certificates" in REMOTES[0].get_relation(out).remote_app_data
    assert isinstance(out.unit_status, ops.testing.ActiveStatus)


def test_integrate_default_end_is_received(requirer_ctx: _Ctx, mocked: None):
    explicit = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="received"
    )
    default = REMOTES[0].integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    assert explicit.unit_status == default.unit_status
    assert len(_certificate_secrets(explicit)) == len(_certificate_secrets(default))


def test_integrate_preserves_other_state(requirer_ctx: _Ctx, mocked: None):
    other = ops.testing.Relation("other-endpoint", remote_app_data={"key": "value"})
    state = ops.testing.State(relations=[other], config={})
    out = REMOTES[0].integrate(requirer_ctx, state)
    assert _relation(out, other.id).remote_app_data == {"key": "value"}


def test_integrate_propagates_charm_errors(mocked: None):
    """OP093: exceptions raised while the charm executes propagate. This is user error."""

    class BrokenCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            framework.observe(self.on["certificates"].relation_created, self._boom)

        def _boom(self, _: ops.EventBase) -> None:
            raise RuntimeError("the charm is broken")

    ctx = ops.testing.Context(BrokenCharm, meta=requirer_charm.META)
    with pytest.raises(ops.testing.errors.UncaughtCharmError, match="the charm is broken"):
        REMOTES[0].integrate(ctx, ops.testing.State())


# ------------------------------------------------------------------- run_changed contract


def test_run_changed_is_equivalent_to_one_ctx_run(requirer_ctx: _Ctx, mocked: None):
    """OP093 specifies the equivalence, so it is worth pinning."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    before = len(requirer_ctx.emitted_events)
    via_method = REMOTES[0].run_changed(requirer_ctx, state)
    after = len(requirer_ctx.emitted_events)
    # One relation-changed, plus whatever the charm's own observers emit in response --
    # which is exactly what the equivalent ctx.run would emit too.
    changed = [
        e
        for e in requirer_ctx.emitted_events[before:after]
        if isinstance(e, ops.RelationChangedEvent)
    ]
    assert len(changed) == 1
    relation = REMOTES[0].get_relation(state)
    assert changed[0].relation.id == relation.id
    # And spelled out in full, the expression the method stands for produces the same state.
    via_ctx_run = requirer_ctx.run(
        requirer_ctx.on.relation_changed(relation, remote_unit=0), state
    )
    assert via_method.unit_status == via_ctx_run.unit_status
    assert REMOTES[0].get_relation(via_method).local_unit_data == (
        REMOTES[0].get_relation(via_ctx_run).local_unit_data
    )


def test_run_changed_names_the_remote_unit(requirer_ctx: _Ctx, mocked: None):
    """The remote has one unit, so say so rather than let ops.testing warn about it."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    before = len(requirer_ctx.emitted_events)
    REMOTES[0].run_changed(requirer_ctx, state)
    event = next(
        e for e in requirer_ctx.emitted_events[before:] if isinstance(e, ops.RelationChangedEvent)
    )
    assert event.unit is not None
    assert event.unit.name == "remote/0"


def test_run_changed_raises_without_a_relation(requirer_ctx: _Ctx, mocked: None):
    with pytest.raises(KeyError, match="no relation"):
        REMOTES[0].run_changed(requirer_ctx, ops.testing.State())


# ----------------------------------------------------------- RemoteProvider: what it writes


def test_provider_derives_its_answer_from_what_the_charm_published(
    requirer_ctx: _Ctx, mocked: None
):
    """The conformance test OP093 requires: two charms asking for different things.

    A provider that ignored the charm's relation data and wrote canned values would satisfy
    every other clause of the spec while reintroducing exactly the silent mismatches the
    package exists to prevent. This is the one property that can't be checked by reading a
    signature.
    """
    first = [tls_certificates.CertificateRequestAttributes(common_name="first.example.com")]
    second = [
        tls_certificates.CertificateRequestAttributes(common_name="second.example.com"),
        tls_certificates.CertificateRequestAttributes(common_name="third.example.com"),
    ]
    published: list[set[str]] = []
    for requests in (first, second):
        ctx = ops.testing.Context(_charm_requesting(requests), meta=requirer_charm.META)
        state = REMOTES[0].integrate(ctx, ops.testing.State.from_context(ctx))
        certificates = json.loads(REMOTES[0].get_relation(state).remote_app_data["certificates"])
        published.append({
            tls_certificates.Certificate.from_string(c["certificate"]).common_name
            for c in certificates
        })
    assert published[0] == {"first.example.com"}
    assert published[1] == {"second.example.com", "third.example.com"}
    assert published[0] != published[1]


def test_provider_answers_the_charms_own_key(requirer_ctx: _Ctx, mocked: None):
    """Derivation means the certificate is bound to whatever key the charm actually used.

    Under the previous API this was the coupling that failed silently: the fixture signed
    with its own key, and a charm using a different one simply saw no certificates.
    """
    state = REMOTES[0].integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    assert key is not None
    assert assigned
    for certificate in assigned:
        assert certificate.certificate.matches_private_key(key)


def test_provider_publishes_a_real_chain(requirer_ctx: _Ctx, mocked: None):
    """Leaf to root, signed by a genuine CA, so chain verification succeeds."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    for entry in json.loads(REMOTES[0].get_relation(state).remote_app_data["certificates"]):
        chain = entry["chain"]
        assert chain[0].strip() == entry["certificate"].strip()
        assert chain[-1].strip() == entry["ca"].strip()
        assert tls_certificates.chain_has_valid_order(chain)


def test_provider_answers_a_ca_request_with_a_ca_certificate(mocked: None):
    """The library matches on both the databag's ca flag and BasicConstraints."""
    requests = [
        tls_certificates.CertificateRequestAttributes(common_name="ca.example.com", is_ca=True)
    ]
    ctx = ops.testing.Context(_charm_requesting(requests), meta=requirer_charm.META)
    state = REMOTES[0].integrate(ctx, ops.testing.State.from_context(ctx), end="published")
    entry = json.loads(REMOTES[0].get_relation(state).remote_app_data["certificates"])[0]
    assert tls_certificates.Certificate.from_string(entry["certificate"]).is_ca
    # ... while an ordinary request gets a leaf certificate.
    state = REMOTES[0].integrate(
        ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META),
        ops.testing.State(),
        end="published",
    )
    entry = json.loads(REMOTES[0].get_relation(state).remote_app_data["certificates"])[0]
    assert not tls_certificates.Certificate.from_string(entry["certificate"]).is_ca


def test_provider_publish_is_idempotent(requirer_ctx: _Ctx, mocked: None):
    """OP093: calling it twice with nothing else changed leaves the state unchanged."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    once = REMOTES[0].get_relation(state).remote_app_data
    twice = REMOTES[0].get_relation(REMOTES[0].publish(state)).remote_app_data
    assert twice == once


def test_a_re_request_is_distinguishable_from_the_request_it_replaces(
    requirer_ctx: _Ctx, mocked: None
):
    """The wire-format property that every renewal test rests on.

    The library tells requests apart by the unique identifier in the subject name, and
    ``mocked`` replaces that identifier with a sequence rather than a constant. Were it ever
    a constant, a re-request would be byte-identical to the request it replaces: the provider
    would see a request it had already answered, keep the stale certificate, and every
    renewal test would still pass while exercising nothing. This is the guard for that.
    """
    stale = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.renewing()
    )
    state = stale.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    answered = {
        entry["certificate_signing_request"]
        for entry in json.loads(stale.get_relation(state).remote_app_data["certificates"])
    }
    # A reconcile: the safety net withdraws the stale requests and re-requests.
    relation = stale.get_relation(stale.run_changed(requirer_ctx, state))
    requested = {
        entry["certificate_signing_request"]
        for databag in (relation.local_app_data, relation.local_unit_data)
        for entry in json.loads(databag.get("certificate_signing_requests", "[]"))
    }
    assert answered
    assert requested
    assert answered.isdisjoint(requested)


def test_provider_publish_drops_answers_to_withdrawn_requests(requirer_ctx: _Ctx, mocked: None):
    """What the real provider's library does when a request disappears."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    relation = REMOTES[0].get_relation(state)
    assert json.loads(relation.remote_app_data["certificates"])
    withdrawn = dataclasses.replace(
        relation, local_unit_data={"certificate_signing_requests": "[]"}
    )
    state = dataclasses.replace(state, relations={withdrawn})
    out = REMOTES[0].publish(state)
    assert not _interface_keys(REMOTES[0].get_relation(out).remote_app_data)


def test_provider_publish_keeps_existing_certificates_byte_for_byte(
    requirer_ctx: _Ctx, mocked: None
):
    """Signing is non-deterministic, so re-signing would break idempotence and assertions."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    before = json.loads(REMOTES[0].get_relation(state).remote_app_data["certificates"])
    after = json.loads(
        REMOTES[0].get_relation(REMOTES[0].publish(state)).remote_app_data["certificates"]
    )
    assert [c["certificate"] for c in after] == [c["certificate"] for c in before]


def test_provider_publish_tolerates_unreadable_provider_data(requirer_ctx: _Ctx, mocked: None):
    """The library degrades rather than raising, so a test can construct this state."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="integrated"
    )
    relation = REMOTES[0].get_relation(state)
    state = dataclasses.replace(
        state, relations={dataclasses.replace(relation, remote_app_data={"certificates": "nope"})}
    )
    out = REMOTES[0].publish(state)
    certificates = json.loads(REMOTES[0].get_relation(out).remote_app_data["certificates"])
    assert len(certificates) == len(requirer_charm.REQUESTS)


def test_provider_rejects_a_second_remote_on_one_endpoint(requirer_ctx: _Ctx, mocked: None):
    """OP093: a library that doesn't support several remotes per endpoint must raise.

    The requirer library reads its relation with Model.get_relation, which raises when an
    endpoint carries more than one -- so silently building this state would hand the caller
    a charm that can't complete a hook.
    """
    state = REMOTES[0].integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    second = tls_certificates_testing.RemoteProvider("certificates", remote_app_name="other-ca")
    with pytest.raises(ValueError, match="only one provider per endpoint"):
        second.integrate(requirer_ctx, state)


# ------------------------------------------------------------------------------- Outcome

_Outcome = tls_certificates_testing.Outcome
"""Alias, because the assertions below compare several outcomes per line."""


def test_outcome_no_argument_constructors_are_singletons():
    """Outcome.issued() is Outcome.issued(): no reason for two instances to ever differ."""
    assert tls_certificates_testing.Outcome.issued() is tls_certificates_testing.Outcome.issued()
    assert (
        tls_certificates_testing.Outcome.renewing() is tls_certificates_testing.Outcome.renewing()
    )
    assert tls_certificates_testing.Outcome.expired() is tls_certificates_testing.Outcome.expired()
    assert tls_certificates_testing.Outcome.revoked() is tls_certificates_testing.Outcome.revoked()


def test_outcome_denied_constructs_fresh_each_call():
    """Unlike the others, denied() carries per-call arguments, so it can't be a singleton."""
    assert (
        tls_certificates_testing.Outcome.denied() is not tls_certificates_testing.Outcome.denied()
    )


def test_outcome_equality():
    assert _Outcome.denied() == _Outcome.denied()
    assert _Outcome.issued() == _Outcome.issued()
    assert _Outcome.issued() != _Outcome.denied()
    assert _Outcome.issued() != _Outcome.renewing()
    assert _Outcome.denied(
        code=tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
    ) != _Outcome.denied(code=tls_certificates.CertificateRequestErrorCode.IP_NOT_ALLOWED)
    assert _Outcome.denied(message="a") != _Outcome.denied(message="b")
    assert _Outcome.denied(reason="a") != _Outcome.denied(reason="b")
    assert _Outcome.issued() != object()
    assert _Outcome.issued().__eq__(object()) is NotImplemented


def test_outcome_hash_is_consistent_with_equality():
    assert hash(_Outcome.denied()) == hash(_Outcome.denied())
    assert hash(_Outcome.issued()) == hash(_Outcome.issued())
    seen = {_Outcome.issued(), _Outcome.denied(), _Outcome.denied()}
    assert seen == {_Outcome.issued(), _Outcome.denied()}


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (tls_certificates_testing.Outcome.issued(), "Outcome.issued()"),
        (tls_certificates_testing.Outcome.renewing(), "Outcome.renewing()"),
        (tls_certificates_testing.Outcome.expired(), "Outcome.expired()"),
        (tls_certificates_testing.Outcome.revoked(), "Outcome.revoked()"),
        (tls_certificates_testing.Outcome.denied(), "Outcome.denied()"),
        (
            tls_certificates_testing.Outcome.denied(
                code=tls_certificates.CertificateRequestErrorCode.SERVER_NOT_AVAILABLE,
                message="the server is unavailable",
                reason="maintenance",
            ),
            "Outcome.denied(code=CertificateRequestErrorCode.SERVER_NOT_AVAILABLE, "
            "message='the server is unavailable', reason='maintenance')",
        ),
    ],
    ids=["issued", "renewing", "expired", "revoked", "denied-defaults", "denied-customised"],
)
def test_outcome_repr(outcome: tls_certificates_testing.Outcome, expected: str):
    assert repr(outcome) == expected


@pytest.mark.parametrize(
    "outcome",
    [
        tls_certificates_testing.Outcome.issued(),
        tls_certificates_testing.Outcome.renewing(),
        tls_certificates_testing.Outcome.expired(),
        tls_certificates_testing.Outcome.revoked(),
    ],
    ids=["issued", "renewing", "expired", "revoked"],
)
def test_outcome_fields_are_none_for_every_non_denied_outcome(
    outcome: tls_certificates_testing.Outcome,
):
    assert outcome.code is None
    assert outcome.message is None
    assert outcome.reason is None


def test_outcome_denied_fields_are_readable():
    outcome = tls_certificates_testing.Outcome.denied(
        code=tls_certificates.CertificateRequestErrorCode.WILDCARD_NOT_ALLOWED,
        message="no wildcards",
        reason="policy",
    )
    assert outcome.code is tls_certificates.CertificateRequestErrorCode.WILDCARD_NOT_ALLOWED
    assert outcome.message == "no wildcards"
    assert outcome.reason == "policy"


# -------------------------------------------------------------- RemoteProvider: outcomes


def test_outcome_denied(mocked: None):
    requests = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        outcome=tls_certificates_testing.Outcome.denied(
            code=tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED,
            message="that domain is not allowed",
            reason="policy",
        ),
    )
    ctx = ops.testing.Context(_charm_requesting(requests), meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State.from_context(ctx), end="published")
    databag = remote.get_relation(state).remote_app_data
    # The request is still in the charm's databag -- it asked -- but there's no certificate.
    assert "certificates" not in databag
    errors = json.loads(databag["request_errors"])
    assert len(errors) == 1
    code = tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
    assert errors[0]["error"]["code"] == code.value
    assert errors[0]["error"]["name"] == code.name
    assert errors[0]["error"]["message"] == "that domain is not allowed"
    assert errors[0]["error"]["reason"] == "policy"


def test_outcome_denied_defaults(mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.denied()
    )
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State(), end="published")
    errors = json.loads(remote.get_relation(state).remote_app_data["request_errors"])
    code = tls_certificates.CertificateRequestErrorCode.OTHER
    assert all(e["error"]["code"] == code.value for e in errors)


def test_outcome_callable_selects_per_request(mocked: None):
    """Mixed outcomes in one relation: a provider that refuses one domain serves the others."""
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        outcome=lambda request: (
            tls_certificates_testing.Outcome.denied()
            if request.common_name.startswith("egg")
            else tls_certificates_testing.Outcome.issued()
        ),
    )
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State(), end="published")
    databag = remote.get_relation(state).remote_app_data
    issued = {
        tls_certificates.Certificate.from_string(c["certificate"]).common_name
        for c in json.loads(databag["certificates"])
    }
    denied = {
        tls_certificates.CertificateSigningRequest.from_string(e["csr"]).common_name
        for e in json.loads(databag["request_errors"])
    }
    assert issued == {"example.com"}
    assert denied == {"eggsample.com"}


def test_outcome_callable_receives_the_charms_attributes(mocked: None):
    """Reconstructed from the wire, so the callable selects on the request not the format."""
    seen: list[tls_certificates.CertificateRequestAttributes] = []

    def choose(
        request: tls_certificates.CertificateRequestAttributes,
    ) -> tls_certificates_testing.Outcome:
        seen.append(request)
        return tls_certificates_testing.Outcome.issued()

    requests = [
        tls_certificates.CertificateRequestAttributes(
            common_name="example.com", sans_dns={"a.example.com"}, organization="Canonical"
        )
    ]
    remote = tls_certificates_testing.RemoteProvider("certificates", outcome=choose)
    ctx = ops.testing.Context(_charm_requesting(requests), meta=requirer_charm.META)
    remote.integrate(ctx, ops.testing.State.from_context(ctx), end="published")
    assert len(seen) == 1
    assert seen[0].common_name == "example.com"
    assert seen[0].sans_dns == {"a.example.com"}
    assert seen[0].organization == "Canonical"


def test_outcome_callable_must_return_an_outcome(mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        outcome=lambda _: "issued",  # pyright: ignore[reportArgumentType]
    )
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    with pytest.raises(TypeError, match=r"not a tls_certificates_testing\.Outcome"):
        remote.integrate(ctx, ops.testing.State(), end="published")


def test_outcome_renewing_is_past_the_libraries_threshold(mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.renewing()
    )
    certificate = _one_certificate(remote, mocked)
    now = datetime.datetime.now(datetime.timezone.utc)
    start, end = certificate.validity_start_time, certificate.expiry_time
    # min(0.99, default 0.9 + 0.05); past the threshold, but not yet expired.
    threshold = start + (end - start) * 0.95
    assert threshold <= now < end


@pytest.mark.parametrize("renewal_relative_time", [0.51, 0.9, 0.95, 1.0])
def test_outcome_renewing_covers_every_legal_renewal_relative_time(
    renewal_relative_time: float, mocked: None
):
    """No coupling to the charm's renewal_relative_time, because the library caps it.

    That is why there is no argument here for the test author to get silently wrong.
    """
    from charmlibs.interfaces.tls_certificates import _tls_certificates as internal

    remote = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.renewing()
    )
    certificate = _one_certificate(remote, mocked)
    threshold = internal._renewal_safety_threshold(renewal_relative_time)
    now = datetime.datetime.now(datetime.timezone.utc)
    start, end = certificate.validity_start_time, certificate.expiry_time
    assert start + (end - start) * threshold <= now < end


def test_outcome_expired(mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.expired()
    )
    certificate = _one_certificate(remote, mocked)
    assert certificate.expiry_time < datetime.datetime.now(datetime.timezone.utc)


@pytest.mark.parametrize(
    "outcome",
    [
        tls_certificates_testing.Outcome.renewing(),
        tls_certificates_testing.Outcome.expired(),
    ],
    ids=["renewing", "expired"],
)
def test_back_dating_keeps_the_chain_and_the_key_binding(
    outcome: tls_certificates_testing.Outcome, mocked: None
):
    """Back-dating rebuilds the certificate by hand, so this is worth checking."""
    remote = tls_certificates_testing.RemoteProvider("certificates", outcome=outcome)
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State(), end="published")
    for entry in json.loads(remote.get_relation(state).remote_app_data["certificates"]):
        certificate = tls_certificates.Certificate.from_string(entry["certificate"])
        csr = tls_certificates.CertificateSigningRequest.from_string(
            entry["certificate_signing_request"]
        )
        assert csr.matches_certificate(certificate)
        assert tls_certificates.chain_has_valid_order(entry["chain"])


def test_outcome_revoked(mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.revoked()
    )
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State(), end="published")
    entries = json.loads(remote.get_relation(state).remote_app_data["certificates"])
    assert entries
    assert all(e["revoked"] is True for e in entries)
    # ... and an ordinary certificate is not flagged.
    state = REMOTES[0].integrate(
        ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META),
        ops.testing.State(),
        end="published",
    )
    entries = json.loads(REMOTES[0].get_relation(state).remote_app_data["certificates"])
    assert all(e.get("revoked") in (None, False) for e in entries)


def test_provider_validity_is_configurable(mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates", validity=datetime.timedelta(days=7)
    )
    certificate = _one_certificate(remote, mocked)
    span = certificate.expiry_time - certificate.validity_start_time
    assert span == datetime.timedelta(days=7)


# ---------------------------------------------------------- RemoteProvider: capabilities


def test_capabilities_absent_by_default(requirer_ctx: _Ctx, mocked: None):
    """Absent means "not advertised yet", which is distinct from an empty object."""
    state = REMOTES[0].integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    assert "capabilities" not in REMOTES[0].get_relation(state).remote_app_data


def test_capabilities_are_published_when_given(mocked: None):
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=False),
    )
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State(), end="published")
    published = json.loads(remote.get_relation(state).remote_app_data["capabilities"])
    # advertised-as-unsupported (False) must survive as distinct from unspecified (None)
    assert published["supports_wildcard_dns"] is False


def test_capabilities_are_published_before_any_answer(mocked: None):
    """A provider can advertise before it answers anything."""
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        capabilities=tls_certificates.ProviderCapabilities(),
        outcome=tls_certificates_testing.Outcome.denied(),
    )
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State(), end="published")
    databag = remote.get_relation(state).remote_app_data
    assert "capabilities" in databag
    assert "certificates" not in databag


def test_capabilities_survive_publishing_again(requirer_ctx: _Ctx, mocked: None):
    """Answering requests must not un-advertise what the provider already said."""
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        capabilities=tls_certificates.ProviderCapabilities(supports_ip_sans=True),
    )
    state = remote.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    state = remote.publish(state)
    databag = remote.get_relation(state).remote_app_data
    assert json.loads(databag["capabilities"])["supports_ip_sans"] is True
    assert "certificates" in databag


# ------------------------------------------------------------ RemoteRequirer: what it writes


def test_requirer_writes_its_requests_to_the_unit_databag_by_default(
    provider_ctx: _Ctx, mocked: None
):
    remote = tls_certificates_testing.RemoteRequirer("certificates")
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    relation = remote.get_relation(state)
    assert "certificate_signing_requests" in relation.remote_units_data[0]
    assert not _interface_keys(relation.remote_app_data)


def test_requirer_mode_app(provider_ctx: _Ctx, mocked: None):
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates", mode=tls_certificates.Mode.APP
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    relation = remote.get_relation(state)
    assert "certificate_signing_requests" in relation.remote_app_data
    assert set(relation.remote_units_data[0]) <= JUJU_NETWORK_KEYS


def test_requirer_mode_app_and_unit_splits_the_requests(provider_ctx: _Ctx, mocked: None):
    app = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
    unit = tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={
            tls_certificates.Mode.APP: [app],
            tls_certificates.Mode.UNIT: [unit],
        },
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    relation = remote.get_relation(state)
    assert _common_names(relation.remote_app_data) == {"app.example.com"}
    assert _common_names(relation.remote_units_data[0]) == {"unit.example.com"}


def test_requirer_mode_app_and_unit_defaults_to_one_request_per_scope(
    provider_ctx: _Ctx, mocked: None
):
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates", mode=tls_certificates.Mode.APP_AND_UNIT
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    relation = remote.get_relation(state)
    app = _common_names(relation.remote_app_data)
    unit = _common_names(relation.remote_units_data[0])
    assert app
    assert unit
    assert app.isdisjoint(unit)  # distinct, as the library requires of APP_AND_UNIT requests


def test_requirer_mode_app_and_unit_accepts_a_single_scope(provider_ctx: _Ctx, mocked: None):
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={
            tls_certificates.Mode.UNIT: [
                tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
            ]
        },
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    relation = remote.get_relation(state)
    assert _common_names(relation.remote_units_data[0]) == {"unit.example.com"}
    assert not _interface_keys(relation.remote_app_data)


def test_requirer_signs_with_its_own_key(provider_ctx: _Ctx, mocked: None):
    key = tls_certificates.PrivateKey.generate()
    remote = tls_certificates_testing.RemoteRequirer("certificates", private_key=key)
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    entries = json.loads(
        remote.get_relation(state).remote_units_data[0]["certificate_signing_requests"]
    )
    for entry in entries:
        csr = tls_certificates.CertificateSigningRequest.from_string(
            entry["certificate_signing_request"]
        )
        assert csr.matches_private_key(key)


def test_requirer_flags_a_ca_request(provider_ctx: _Ctx, mocked: None):
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates",
        certificate_requests=[
            tls_certificates.CertificateRequestAttributes(common_name="ca.example.com", is_ca=True)
        ],
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    entries = json.loads(
        remote.get_relation(state).remote_units_data[0]["certificate_signing_requests"]
    )
    assert entries[0]["ca"] is True


def test_requirer_publish_is_idempotent(provider_ctx: _Ctx, mocked: None):
    """The requests must not be re-signed, or the charm's certificates would be orphaned."""
    remote = tls_certificates_testing.RemoteRequirer("certificates")
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    once = remote.get_relation(state).remote_units_data[0]
    twice = remote.get_relation(remote.publish(state)).remote_units_data[0]
    assert twice == once


def test_requirer_publish_removes_requests_it_no_longer_makes(provider_ctx: _Ctx, mocked: None):
    """What a real requirer's library does when its configuration changes."""
    keep = tls_certificates.CertificateRequestAttributes(common_name="keep.example.com")
    drop = tls_certificates.CertificateRequestAttributes(common_name="drop.example.com")
    before = tls_certificates_testing.RemoteRequirer(
        "certificates", certificate_requests=[keep, drop]
    )
    after = tls_certificates_testing.RemoteRequirer("certificates", certificate_requests=[keep])
    state = before.integrate(provider_ctx, ops.testing.State(leader=True))
    assert _common_names(before.get_relation(state).remote_units_data[0]) == {
        "keep.example.com",
        "drop.example.com",
    }
    state = after.publish(state)
    assert _common_names(after.get_relation(state).remote_units_data[0]) == {"keep.example.com"}


def test_requirer_publish_leaves_the_charms_certificates_alone(provider_ctx: _Ctx, mocked: None):
    """Only the remote's side is written, so the charm's answers survive."""
    remote = tls_certificates_testing.RemoteRequirer("certificates")
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True))
    before = remote.get_relation(state).local_app_data
    assert "certificates" in before
    state = remote.publish(state)
    assert remote.get_relation(state).local_app_data == before


def test_requirer_supports_several_remotes_on_one_endpoint(provider_ctx: _Ctx, mocked: None):
    """A provider charm may serve several requirer applications on one endpoint."""
    workers = [
        tls_certificates_testing.RemoteRequirer(
            "certificates",
            remote_app_name=f"worker{n}",
            certificate_requests=[
                tls_certificates.CertificateRequestAttributes(common_name=f"worker{n}.example.com")
            ],
        )
        for n in range(3)
    ]
    state = ops.testing.State(leader=True)
    for worker in workers:
        state = worker.integrate(provider_ctx, state)
    assert len(state.get_relations("certificates")) == 3
    for n, worker in enumerate(workers):
        relation = worker.get_relation(state)
        assert _common_names(relation.remote_units_data[0]) == {f"worker{n}.example.com"}


def test_requirer_request_arguments_are_validated():
    """Mirror the pairing rules the library enforces on a real requirer's own arguments.

    The annotations already rule some of these out, but a caller without a type checker can
    still pass them, so they must be checked at runtime too -- APP_AND_UNIT as a key would
    otherwise reach the databag.
    """
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    by_mode: dict[_Scope, list[tls_certificates.CertificateRequestAttributes]] = {
        tls_certificates.Mode.UNIT: [request]
    }
    cls = tls_certificates_testing.RemoteRequirer
    with pytest.raises(ValueError, match="mutually exclusive"):
        cls("certificates", certificate_requests=[request], certificate_requests_by_mode=by_mode)
    with pytest.raises(ValueError, match=r"only valid when mode is Mode\.APP_AND_UNIT"):
        cls("certificates", certificate_requests_by_mode=by_mode)
    with pytest.raises(ValueError, match=r"must not be given when mode is Mode\.APP_AND_UNIT"):
        cls(
            "certificates",
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests=[request],
        )
    with pytest.raises(ValueError, match=r"keys must be Mode\.APP or Mode\.UNIT"):
        cls(
            "certificates",
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests_by_mode={  # pyright: ignore[reportArgumentType]
                tls_certificates.Mode.APP_AND_UNIT: [request]
            },
        )
    with pytest.raises(ValueError, match="mode must be"):
        cls("certificates", mode="unit")  # pyright: ignore[reportArgumentType]


def test_requirer_normalises_its_request_iterables(provider_ctx: _Ctx, mocked: None):
    """A remote is reused across tests, so a one-shot iterator must not be consumed once."""
    requests = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates", certificate_requests=iter(requests)
    )
    first = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    second = remote.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    assert _common_names(remote.get_relation(first).remote_units_data[0]) == {"example.com"}
    assert _common_names(remote.get_relation(second).remote_units_data[0]) == {"example.com"}


# --------------------------------------------------------------------------------- helpers


_Ctx: typing.TypeAlias = "ops.testing.Context[typing.Any]"


def _charm_requesting(
    requests: list[tls_certificates.CertificateRequestAttributes],
) -> type[ops.CharmBase]:
    """Return a requirer charm class asking for exactly ``requests``."""

    class Charm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="certificates",
                certificate_requests=requests,
            )

    return Charm


def _one_certificate(
    remote: tls_certificates_testing.RemoteProvider, mocked: None
) -> tls_certificates.Certificate:
    """Integrate a one-request charm and return the single certificate published for it."""
    requests = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]
    ctx = ops.testing.Context(_charm_requesting(requests), meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State.from_context(ctx), end="published")
    entries = json.loads(remote.get_relation(state).remote_app_data["certificates"])
    assert len(entries) == 1
    return tls_certificates.Certificate.from_string(entries[0]["certificate"])


def _certificate_secrets(state: ops.testing.State) -> list[ops.testing.Secret]:
    """Return the secrets the library created to store assigned certificates.

    The private key secret uses the same LIBID prefix, so filter on the infix -- that is the
    library's own naming, in `_get_csr_secret_label`.
    """
    return [s for s in state.secrets if s.label and "-certificate-" in s.label]


def _relation(state: ops.testing.State, relation_id: int) -> ops.testing.Relation:
    """Fetch a relation by id, narrowed from RelationBase, which has no databag attributes."""
    found = state.get_relation(relation_id)
    assert isinstance(found, ops.testing.Relation)
    return found


def _interface_keys(databag: typing.Mapping[str, str]) -> set[str]:
    """Return only the interface's own keys, excluding Juju's network ones."""
    return set(databag) - JUJU_NETWORK_KEYS


def _common_names(databag: typing.Mapping[str, str]) -> set[str]:
    """Return the common names of the certificate requests in a requirer databag."""
    entries: Iterable[dict[str, str]] = json.loads(
        databag.get("certificate_signing_requests", "[]")
    )
    return {
        tls_certificates.CertificateSigningRequest.from_string(
            entry["certificate_signing_request"]
        ).common_name
        for entry in entries
    }
