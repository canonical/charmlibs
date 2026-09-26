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

"""Tests from a requirer charm's perspective -- how a charm author would use the package.

These assert on the charm and on the library's accessors, never on relation data. Not having
to touch the wire format is the point of the package; test_testing.py is where the wire
format is the subject.

The charm here lets the library manage its private key, the recommended configuration. See
test_requirer_charm_manual.py for one that supplies its own.
"""

from __future__ import annotations

import dataclasses
import datetime
import typing

import ops
import ops.testing

import requirer_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

CERTS = tls_certificates_testing.RemoteProvider("certificates")
REQUESTED = {r.common_name for r in requirer_charm.REQUESTS}

_Ctx: typing.TypeAlias = "ops.testing.Context[requirer_charm.RequirerCharm]"


def test_no_relation(requirer_ctx: _Ctx, mocked: None):
    """Sanity check: no relation, no certificates."""
    with requirer_ctx(requirer_ctx.on.update_status(), ops.testing.State()) as manager:
        state_out = manager.run()
        assert manager.charm.certs is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_bare_relation(requirer_ctx: _Ctx, mocked: None):
    """A relation with nothing written on it -- below `end="integrated"`.

    Built by hand from the remote's own attributes, so that the remote can still find it.
    """
    relation = ops.testing.Relation(
        CERTS.endpoint, interface="tls-certificates", remote_app_name=CERTS.remote_app_name
    )
    state = ops.testing.State(relations=[relation])
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assert manager.charm.certs is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    # And the remote agrees with it, which is what reading those attributes is for.
    assert CERTS.get_relation(state_out).id == relation.id


def test_the_happy_path_is_one_line(requirer_ctx: _Ctx, mocked: None):
    """The whole conversation, with nothing to keep in agreement with the charm."""
    state_out = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_the_charm_holds_the_certificates_it_asked_for(requirer_ctx: _Ctx, mocked: None):
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.certs is not None
        assert {c.common_name for c in manager.charm.certs} == REQUESTED


def test_integrated_means_asked_but_unanswered(requirer_ctx: _Ctx, mocked: None):
    """The most common real intermediate state.

    The charm should report blocked because the provider hasn't answered -- not because it
    failed to ask.
    """
    state = CERTS.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="integrated"
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    # The charm's requests made it to the relation, and it holds a key ...
    assert {c.certificate_signing_request.common_name for c in csrs} == REQUESTED
    assert key is not None
    # ... but nothing has been issued for them.
    assert not assigned
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_published_means_answered_but_not_yet_seen(requirer_ctx: _Ctx, mocked: None):
    """The answer is on the wire; the charm reconciles when it next runs."""
    state = CERTS.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_certificates_are_bound_to_the_charms_key(requirer_ctx: _Ctx, mocked: None):
    """The property that makes the fixture impossible to silently disagree with.

    The provider signed the requests the charm actually published, so the certificates match
    whatever key the charm used -- no key to seed, and no silent "no certificates".
    """
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    assert key is not None
    assert assigned
    for certificate in assigned:
        assert certificate.certificate.matches_private_key(key)
        assert certificate.certificate_signing_request.matches_certificate(certificate.certificate)


def test_certificate_available_fires_on_every_reconcile(requirer_ctx: _Ctx, mocked: None):
    """The library's event is level-triggered, not a change signal.

    It fires even when the stored secret already holds exactly the certificate on the
    relation, so charms must reconcile against installed state. Pin that as documented
    behaviour rather than an accident.
    """
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    before = len(_available(requirer_ctx))
    reconciles = 3
    for _ in range(reconciles):
        state = CERTS.run_changed(requirer_ctx, state)
    fired = _available(requirer_ctx)[before:]
    assert len(fired) == reconciles * len(requirer_charm.REQUESTS)
    assert {e.certificate.common_name for e in fired} == REQUESTED


def test_the_settled_relation_is_stable(requirer_ctx: _Ctx, mocked: None):
    """Repeated reconciles must not rewrite the relation or trip certificate renewal.

    Issued certificates start at 0% of their validity, well short of the library's renewal
    threshold. If that regressed -- by issuing nearly-expired certificates, say -- the
    library would withdraw the requests and replace them on the first reconcile, invalidating
    every test built on a settled relation staying settled.
    """
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        first, _ = manager.charm.certificates.get_assigned_certificates()
    for _ in range(3):
        state = CERTS.run_changed(requirer_ctx, state)
        state = CERTS.publish(state)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        again, _ = manager.charm.certificates.get_assigned_certificates()
    assert {str(c.certificate) for c in again} == {str(c.certificate) for c in first}
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_key_rotation_round_trip(requirer_ctx: _Ctx, mocked: None):
    """Rotate, re-request, have the provider answer, and check the binding moved."""
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state = manager.run()
        assigned, before = manager.charm.certificates.get_assigned_certificates()
        assert len(assigned) == len(requirer_charm.REQUESTS)
    # The charm rotates: old requests withdrawn, new ones sent, nothing answered yet.
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.charm.certificates.regenerate_private_key()
        state = manager.run()
        assigned, after = manager.charm.certificates.get_assigned_certificates()
        assert after is not None
        assert after != before
        assert not assigned
    # The provider answers the fresh requests, and the charm picks them up.
    state = CERTS.publish(state)
    state = CERTS.run_changed(requirer_ctx, state)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assigned, final = manager.charm.certificates.get_assigned_certificates()
    assert final == after
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert before is not None
    for certificate in assigned:
        assert certificate.certificate.matches_private_key(after)
        assert not certificate.certificate.matches_private_key(before)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_renewal_round_trip(requirer_ctx: _Ctx, mocked: None):
    """A stale certificate, the library's safety net, and the provider's fresh answer.

    Two remotes for the same application: one that issues stale certificates, one that
    issues good ones. A remote is immutable and depends only on its arguments and the state,
    so this is just two ways of answering.
    """
    stale = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.renewing()
    )
    state = stale.integrate(
        requirer_ctx, ops.testing.State.from_context(requirer_ctx), end="published"
    )
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state = manager.run()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
        was_stale = {str(c.certificate) for c in assigned}
        assert len(assigned) == len(requirer_charm.REQUESTS)
    # A reconcile: the safety net withdraws the stale requests and re-requests.
    state = stale.run_changed(requirer_ctx, state)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state = manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
        assert not assigned  # the fresh requests are unanswered
    # The provider answers them properly, completing the renewal.
    fresh = tls_certificates_testing.RemoteProvider("certificates")
    state = fresh.publish(state)
    state = fresh.run_changed(requirer_ctx, state)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assigned, after = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert {str(c.certificate) for c in assigned}.isdisjoint(was_stale)
    assert after == key  # renewal is not rotation: the same key
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_expired_certificates_are_not_renewed(requirer_ctx: _Ctx, mocked: None):
    """The library's safety net stops at expiry, so a dead certificate stays assigned.

    Reaching this state means renewal did not happen, which is what the safety net exists to
    prevent -- so a test built on it is a resilience test, not normal operation. What the
    charm does about it is the charm's own decision.
    """
    expired = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.expired()
    )
    state = expired.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    state = expired.run_changed(requirer_ctx, state)
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    for certificate in assigned:
        assert certificate.certificate.expiry_time < _now()


def test_denied_requests_reach_the_charm(requirer_ctx: _Ctx, mocked: None):
    """One issued, one denied: the realistic case, since a provider that refuses one domain
    still serves the others.
    """
    issued, refused = requirer_charm.REQUESTS
    code = tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        outcome=lambda request: (
            tls_certificates_testing.Outcome.denied(code=code, message="computer says no")
            if request.common_name == refused.common_name
            else tls_certificates_testing.Outcome.issued()
        ),
    )
    state = remote.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
        errors = manager.charm.certificates.get_request_errors()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
        refused_csr = next(
            c.certificate_signing_request
            for c in csrs
            if c.certificate_signing_request.common_name == refused.common_name
        )
        error = manager.charm.certificates.get_request_error(refused_csr)
    # The issued request is assigned as usual ...
    assert {c.certificate.common_name for c in assigned} == {issued.common_name}
    # ... the denied one is reported as a request error ...
    assert [e.certificate_signing_request.common_name for e in errors] == [refused.common_name]
    assert error is not None
    assert error.error.code == code.value
    assert error.error.message == "computer says no"
    # ... and emitted as certificate_denied, alongside the other's certificate_available.
    denied = [
        e
        for e in requirer_ctx.emitted_events
        if isinstance(e, tls_certificates.CertificateDeniedEvent)
    ]
    assert [e.certificate_signing_request.common_name for e in denied] == [refused.common_name]
    assert denied[0].error.code == code.value
    assert {e.certificate.common_name for e in _available(requirer_ctx)} == {issued.common_name}


def test_revoking_a_certificate_removes_its_secret(requirer_ctx: _Ctx, mocked: None):
    """The library removes a revoked certificate's Juju secret on its next reconcile.

    Two remotes for the same application, in sequence: nothing has to agree between them,
    because both answer the requests the charm itself published.
    """
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    before = _certificate_secrets(state)
    assert len(before) == len(requirer_charm.REQUESTS)
    # The provider revokes what it issued.
    revoker = tls_certificates_testing.RemoteProvider(
        "certificates", outcome=tls_certificates_testing.Outcome.revoked()
    )
    state = _forget_the_provider_answer(state)
    state = revoker.publish(state)
    state = revoker.run_changed(requirer_ctx, state)
    assert not _certificate_secrets(state)


def test_a_ca_request_is_answered_with_a_ca_certificate(mocked: None):
    """The library matches on the databag's ca flag and on BasicConstraints, so both agree."""
    request = tls_certificates.CertificateRequestAttributes(
        common_name="ca.example.com", is_ca=True
    )

    class CaCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self, relationship_name="certificates", certificate_requests=[request]
            )

    ctx = ops.testing.Context(CaCharm, meta=requirer_charm.META)
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx))
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert len(assigned) == 1
    assert assigned[0].certificate.common_name == request.common_name
    assert assigned[0].certificate.is_ca


def test_provider_capabilities_are_absent_by_default(requirer_ctx: _Ctx, mocked: None):
    """No capabilities models a provider that hasn't advertised yet.

    Per the library's contract that means `None` -- "not known yet, defer" -- which is
    distinct from advertising an empty set.
    """
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.certificates.get_provider_capabilities() is None


def test_provider_capabilities_reach_the_charm(requirer_ctx: _Ctx, mocked: None):
    """All three field states survive: supported, advertised-as-unsupported, unspecified."""
    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        capabilities=tls_certificates.ProviderCapabilities(
            supports_ip_sans=True, supports_wildcard_dns=False
        ),
    )
    state = remote.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        capabilities = manager.charm.certificates.get_provider_capabilities()
    assert capabilities is not None
    assert capabilities.supports_ip_sans is True
    assert capabilities.supports_wildcard_dns is False
    assert capabilities.supports_subdomain is None  # unspecified, not a default


def test_capability_aware_requests_are_resolved_against_the_advertisement(mocked: None):
    """The callable form of certificate_requests sees what the remote advertised.

    This takes an extra turn, and the reason is worth spelling out, because it is a real
    property of the interface rather than an artifact of the package. The charm asks *first*,
    before the provider has advertised anything, so its first request is the one it makes for
    unknown capabilities. Only once the provider has published does the charm see the
    advertisement, withdraw that request and ask for what the capabilities allow -- which
    nothing has answered yet. `publish` and `run_changed` carry it the rest of the way.

    A test that asserted on the settled state after a single `integrate` would find no
    certificates and look like a bug in the charm. That the package surfaces the extra turn,
    rather than papering over it with canned data, is the point: this is what a real
    deployment does too.
    """
    wildcard = tls_certificates.CertificateRequestAttributes(common_name="*.example.com")
    plain = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    seen: list[tls_certificates.ProviderCapabilities | None] = []

    def choose(
        capabilities: tls_certificates.ProviderCapabilities | None,
    ) -> list[tls_certificates.CertificateRequestAttributes]:
        seen.append(capabilities)
        if capabilities is not None and capabilities.supports_wildcard_dns:
            return [wildcard]
        return [plain]

    class PickyCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self, relationship_name="certificates", certificate_requests=choose
            )

    remote = tls_certificates_testing.RemoteProvider(
        "certificates",
        capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=True),
    )
    ctx = ops.testing.Context(PickyCharm, meta=requirer_charm.META)
    state = remote.integrate(ctx, ops.testing.State.from_context(ctx))
    # The charm asked before the advertisement arrived, so it has now re-asked for the
    # wildcard and nothing has answered that yet.
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
        assert not assigned
    # The provider answers the wildcard request the advertisement produced.
    state = remote.publish(state)
    state = remote.run_changed(ctx, state)
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    # The callable saw the advertised capabilities ...
    assert seen
    assert any(c is not None and c.supports_wildcard_dns for c in seen)
    # ... chose the wildcard request, and that is what got a certificate.
    assert {c.certificate.common_name for c in assigned} == {wildcard.common_name}


def test_a_provider_that_advertises_nothing_gets_the_fallback_request(mocked: None):
    """Companion to the above: unknown capabilities, and the charm's conservative choice.

    Here the charm's first request is also its final one, so one `integrate` settles it --
    which is what makes the extra turn above attributable to the advertisement rather than to
    the callable form itself.
    """
    wildcard = tls_certificates.CertificateRequestAttributes(common_name="*.example.com")
    plain = tls_certificates.CertificateRequestAttributes(common_name="example.com")

    def choose(
        capabilities: tls_certificates.ProviderCapabilities | None,
    ) -> list[tls_certificates.CertificateRequestAttributes]:
        if capabilities is not None and capabilities.supports_wildcard_dns:
            return [wildcard]
        return [plain]

    class PickyCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self, relationship_name="certificates", certificate_requests=choose
            )

    ctx = ops.testing.Context(PickyCharm, meta=requirer_charm.META)
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx))
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == {plain.common_name}


def test_relation_broken(requirer_ctx: _Ctx, mocked: None):
    """get_relation plus an explicit ctx.run, for the events the sequence doesn't cover.

    The library observes relation-broken itself, and drops the certificates it was holding.
    """
    state = CERTS.integrate(requirer_ctx, ops.testing.State.from_context(requirer_ctx))
    with requirer_ctx(requirer_ctx.on.update_status(), state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
        assert assigned
    relation = CERTS.get_relation(state)  # the escape hatch, for an event with no method
    state_out = requirer_ctx.run(requirer_ctx.on.relation_broken(relation), state)
    # The relation is still in the state -- removing it is the caller's job, since
    # ops.testing models relation-broken as an event on a relation that still exists.
    with requirer_ctx(requirer_ctx.on.update_status(), _without(state_out, relation)) as manager:
        state_out = manager.run()
        assert manager.charm.certs is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_a_non_default_unit_finds_its_key(mocked: None):
    """The library's unit-scoped key secret label embeds the unit number.

    Under the previous API this had to be told which unit to seed for, and a mismatch showed
    up as "no certificates" rather than an error. The charm creates its own key here, so
    there is nothing to tell.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META, unit_id=3)
    state = CERTS.integrate(ctx, ops.testing.State.from_context(ctx))
    with ctx(ctx.on.update_status(), state) as manager:
        state_out = manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_several_endpoints_each_with_their_own_provider(mocked: None):
    """A charm related to two certificate providers, one per endpoint."""
    meta = {
        "name": "requirer",
        "requires": {
            "internal-certs": {"interface": "tls-certificates"},
            "public-certs": {"interface": "tls-certificates"},
        },
    }

    class TwoEndpointCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.internal = tls_certificates.TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="internal-certs",
                certificate_requests=[
                    tls_certificates.CertificateRequestAttributes(common_name="internal.example")
                ],
            )
            self.public = tls_certificates.TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="public-certs",
                certificate_requests=[
                    tls_certificates.CertificateRequestAttributes(common_name="public.example")
                ],
            )

    internal = tls_certificates_testing.RemoteProvider("internal-certs")
    public = tls_certificates_testing.RemoteProvider("public-certs")
    ctx = ops.testing.Context(TwoEndpointCharm, meta=meta)
    state = ops.testing.State.from_context(ctx)
    # Written out one remote at a time, rather than looped, so a traceback points at the
    # remote that failed.
    state = internal.integrate(ctx, state)
    state = public.integrate(ctx, state)
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
        internal_certs, _ = manager.charm.internal.get_assigned_certificates()
        public_certs, _ = manager.charm.public.get_assigned_certificates()
    assert {c.certificate.common_name for c in internal_certs} == {"internal.example"}
    assert {c.certificate.common_name for c in public_certs} == {"public.example"}


# --------------------------------------------------------------------------------- helpers


def _available(ctx: _Ctx) -> list[tls_certificates.CertificateAvailableEvent]:
    return [
        e for e in ctx.emitted_events if isinstance(e, tls_certificates.CertificateAvailableEvent)
    ]


def _certificate_secrets(state: ops.testing.State) -> list[ops.testing.Secret]:
    """The secrets the library created to store assigned certificates.

    The private key secret shares the LIBID prefix, so filter on the library's own infix.
    """
    return [s for s in state.secrets if s.label and "-certificate-" in s.label]


def _forget_the_provider_answer(state: ops.testing.State) -> ops.testing.State:
    """Clear the provider's databag, so the next publish answers afresh.

    `publish` keeps answers it has already given, which is what makes it idempotent -- so
    changing the *outcome* for an already-answered request means dropping the old answer
    first. A test that only wants a different outcome from the start doesn't need this;
    construct the remote with that outcome and integrate.
    """
    relation = CERTS.get_relation(state)
    cleared = dataclasses.replace(relation, remote_app_data={})
    others = {r for r in state.relations if r.id != relation.id}
    return dataclasses.replace(state, relations={*others, cleared})


def _without(state: ops.testing.State, relation: ops.testing.Relation) -> ops.testing.State:
    """Return a copy of ``state`` with ``relation`` removed, as Juju does after it breaks."""
    return dataclasses.replace(
        state, relations={r for r in state.relations if r.id != relation.id}
    )


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)
