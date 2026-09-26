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

"""Tests from a provider charm's perspective, using RemoteRequirer.

Note ``leader=True`` throughout. ``TLSCertificatesProvidesV4`` writes to the application
databag, so a non-leader provider charm answers nothing -- which is invisible in the
resulting state.
"""

from __future__ import annotations

import typing

import ops
import ops.testing

import provider_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

REQUEST = tls_certificates.CertificateRequestAttributes(common_name="workload.example.com")
WORKLOAD = tls_certificates_testing.RemoteRequirer("certificates", certificate_requests=[REQUEST])

_Ctx: typing.TypeAlias = "ops.testing.Context[provider_charm.ProviderCharm]"


def test_no_relation(provider_ctx: _Ctx, mocked: None):
    state = ops.testing.State(leader=True)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.requests is None


def test_bare_relation(provider_ctx: _Ctx, mocked: None):
    """A relation with nothing on it. The charm has nothing to sign."""
    relation = ops.testing.Relation(
        WORKLOAD.endpoint,
        interface="tls-certificates",
        remote_app_name=WORKLOAD.remote_app_name,
    )
    state = ops.testing.State(leader=True, relations=[relation])
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.requests is None


def test_the_happy_path_is_one_line(provider_ctx: _Ctx, mocked: None):
    state_out = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True))
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_integrated_means_nothing_to_read_yet(provider_ctx: _Ctx, mocked: None):
    """The provider reads before it writes, so `end="integrated"` is the empty relation.

    Contrast a requirer charm, where `end="integrated"` means it has already asked: which end
    of the conversation writes first is what makes the same value mean different things.
    """
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True), end="integrated")
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.requests is None
        assert not manager.charm.certificates.get_certificate_requests()


def test_published_means_requests_are_waiting(provider_ctx: _Ctx, mocked: None):
    """The requirer has asked, and this charm hasn't answered yet."""
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True), end="published")
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        # Before the run, because this charm answers as soon as it is given the chance -- so
        # "waiting" is only observable ahead of its next reconcile.
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
        assert {r.certificate_signing_request.common_name for r in outstanding} == {
            REQUEST.common_name
        }
        manager.run()
        assert not manager.charm.certificates.get_outstanding_certificate_requests()


def test_received_means_the_charm_has_answered(provider_ctx: _Ctx, mocked: None):
    """The settled relation: nothing left outstanding, and a certificate issued."""
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
        issued = manager.charm.certificates.get_issued_certificates()
    assert not outstanding
    assert {c.certificate.common_name for c in issued} == {REQUEST.common_name}


def test_the_charm_sees_the_requests_it_was_sent(provider_ctx: _Ctx, mocked: None):
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.requests is not None
        assert {r.common_name for r in manager.charm.requests} == {REQUEST.common_name}


def test_the_issued_certificate_matches_the_request(provider_ctx: _Ctx, mocked: None):
    """The charm signed the request the remote actually made, key and all."""
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
    assert issued
    for certificate in issued:
        assert certificate.certificate_signing_request.matches_certificate(certificate.certificate)
        assert certificate.certificate_signing_request.matches_private_key(WORKLOAD.private_key)


def test_a_non_leader_answers_nothing(provider_ctx: _Ctx, mocked: None):
    """Regression guard for the mistake leader=True exists to prevent.

    A non-leader provider charm cannot write its application databag, so it reads the
    requests and then silently issues nothing.
    """
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=False))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        assert manager.charm.requests is not None  # it read them
        assert not manager.charm.certificates.get_provider_certificates()  # but wrote nothing


def test_the_charm_publishes_its_capabilities(provider_ctx: _Ctx, mocked: None):
    """A provider charm advertises when it runs, so this needs no fixture argument."""
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True))
    relation = WORKLOAD.get_relation(state)
    # Reading the databag because this is about what the charm wrote, not what it can read;
    # the library has no accessor for a provider's own advertised capabilities.
    import json

    published = json.loads(relation.local_app_data["capabilities"])
    assert published["provider_type"] == provider_charm.CAPABILITIES.provider_type
    assert published["supports_ca_certificates"] is True


def test_a_multi_application_relation(provider_ctx: _Ctx, mocked: None):
    """Several requirer applications on one endpoint, one remote each.

    This is the case OP093 says a library may support, and the reason a remote is identified
    by endpoint *and* remote_app_name.
    """
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
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
    assert {c.certificate.common_name for c in issued} == {
        f"worker{n}.example.com" for n in range(3)
    }
    assert not outstanding
    # Each remote's relation is separate, and each holds only its own application's answer.
    for n, worker in enumerate(workers):
        relation = worker.get_relation(state)
        certificates = [c for c in issued if c.relation_id == relation.id]
        assert {c.certificate.common_name for c in certificates} == {f"worker{n}.example.com"}


def test_the_requirer_changes_what_it_asks_for(provider_ctx: _Ctx, mocked: None):
    """Later turns from the provider's side: publish the new request, then reconcile.

    The remote writes first here, so `publish` is how the *remote's* configuration changes
    reach the charm -- the mirror of a requirer test, where publish carries the provider's
    answer.
    """
    keep = tls_certificates.CertificateRequestAttributes(common_name="keep.example.com")
    extra = tls_certificates.CertificateRequestAttributes(common_name="extra.example.com")
    before = tls_certificates_testing.RemoteRequirer("certificates", certificate_requests=[keep])
    after = tls_certificates_testing.RemoteRequirer(
        "certificates", certificate_requests=[keep, extra]
    )
    state = before.integrate(provider_ctx, ops.testing.State(leader=True))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
        assert {c.certificate.common_name for c in issued} == {keep.common_name}
    # The requirer adds a request, and the charm answers it without disturbing the first.
    state = after.publish(state)
    state = after.run_changed(provider_ctx, state)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
    assert {c.certificate.common_name for c in issued} == {keep.common_name, extra.common_name}
    assert not outstanding


def test_the_requirer_withdraws_a_request(provider_ctx: _Ctx, mocked: None):
    """The charm removes the certificate for a request that has gone."""
    keep = tls_certificates.CertificateRequestAttributes(common_name="keep.example.com")
    drop = tls_certificates.CertificateRequestAttributes(common_name="drop.example.com")
    before = tls_certificates_testing.RemoteRequirer(
        "certificates", certificate_requests=[keep, drop]
    )
    after = tls_certificates_testing.RemoteRequirer("certificates", certificate_requests=[keep])
    state = before.integrate(provider_ctx, ops.testing.State(leader=True))
    state = after.publish(state)
    state = after.run_changed(provider_ctx, state)
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
    assert {c.certificate.common_name for c in issued} == {keep.common_name}


def test_a_ca_request(provider_ctx: _Ctx, mocked: None):
    """The charm signs a CA request as a CA certificate."""
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates",
        certificate_requests=[
            tls_certificates.CertificateRequestAttributes(common_name="ca.example.com", is_ca=True)
        ],
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
    assert len(issued) == 1
    assert issued[0].certificate.is_ca


def test_an_app_scoped_requirer(provider_ctx: _Ctx, mocked: None):
    """Mode.APP puts the requests in the remote *application* databag, and the charm reads
    both that and every remote unit's.
    """
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates", mode=tls_certificates.Mode.APP, certificate_requests=[REQUEST]
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
    assert {c.certificate.common_name for c in issued} == {REQUEST.common_name}


def test_an_app_and_unit_requirer(provider_ctx: _Ctx, mocked: None):
    """Both scopes' requests reach the charm, and it answers both."""
    remote = tls_certificates_testing.RemoteRequirer(
        "certificates", mode=tls_certificates.Mode.APP_AND_UNIT
    )
    state = remote.integrate(provider_ctx, ops.testing.State(leader=True))
    with provider_ctx(provider_ctx.on.update_status(), state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
    assert len(issued) == 2  # one application request, one unit request
    assert not outstanding


def test_relation_broken(provider_ctx: _Ctx, mocked: None):
    """get_relation plus an explicit ctx.run, as for a requirer charm."""
    state = WORKLOAD.integrate(provider_ctx, ops.testing.State(leader=True))
    relation = WORKLOAD.get_relation(state)
    state_out = provider_ctx.run(provider_ctx.on.relation_broken(relation), state)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
