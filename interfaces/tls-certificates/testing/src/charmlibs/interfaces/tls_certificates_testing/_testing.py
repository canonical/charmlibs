# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The simulated remote applications: :class:`RemoteProvider` and :class:`RemoteRequirer`."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import logging
import typing

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ops import testing

from charmlibs.interfaces import tls_certificates

# The library's private module. Building relation data means writing the interface's wire
# format, which is private: the pydantic models below, the databag encoding and the renewal
# threshold all live here. Reusing them is deliberate -- this package and the library are
# released in lockstep and pin each other exactly, so they cannot drift, whereas a second
# copy of the wire format could. Every use is covered by a test.
from charmlibs.interfaces.tls_certificates import _tls_certificates as _internal

from . import _raw
from ._mocking import require_mocked as _require_mocked

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

logger = logging.getLogger(__name__)

_INTERFACE_NAME = "tls-certificates"
_UNIT_ID = 0
"""The simulated remote application's single unit. See the module docs on units."""
_CA_CERT = tls_certificates.Certificate(raw=_raw.CERT)
_CA_KEY = tls_certificates.PrivateKey(raw=_raw.CA_KEY)
_DEFAULT_KEY = tls_certificates.PrivateKey(raw=_raw.KEY)
_DEFAULT_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="example.com")
_DEFAULT_APP_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
_DEFAULT_UNIT_REQUEST = tls_certificates.CertificateRequestAttributes(
    common_name="unit.example.com"
)
_DEFAULT_VALIDITY = datetime.timedelta(days=42)
_DEFAULT_DENIAL_MESSAGE = "Denied by the simulated provider."

_End: typing.TypeAlias = 'typing.Literal["integrated", "published", "received"]'


class _Kind(enum.Enum):
    """Which of the five things the simulated provider can do with a request. Not public."""

    ISSUED = enum.auto()
    DENIED = enum.auto()
    RENEWING = enum.auto()
    EXPIRED = enum.auto()
    REVOKED = enum.auto()


class Outcome:
    """What the simulated provider does with each certificate request it sees.

    Passed to :class:`RemoteProvider` as ``outcome``, either as a single value applying to
    every request, or as a callable choosing one per request::

        RemoteProvider("certificates", outcome=Outcome.denied())
        RemoteProvider(
            "certificates",
            outcome=lambda request: (
                Outcome.denied() if request.common_name.startswith("*") else Outcome.issued()
            ),
        )

    The callable receives the ``CertificateRequestAttributes`` the charm asked for,
    reconstructed from the request the charm actually published, so a test can select on
    whatever distinguishes its requests -- usually the common name.

    Built through the classmethods below, never by calling ``Outcome()`` directly.
    """

    def __init__(
        self,
        kind: _Kind,
        *,
        code: tls_certificates.CertificateRequestErrorCode | None = None,
        message: str | None = None,
        reason: str | None = None,
    ) -> None:
        # Not part of the public contract -- instances are built through the classmethods
        # below, which is what keeps a denied outcome's fields meaningless on every other
        # kind rather than merely unused.
        self._kind = kind
        self._code = code
        self._message = message
        self._reason = reason

    @classmethod
    def issued(cls) -> Outcome:
        """A certificate, valid from now. The happy path, and the default."""
        return _ISSUED

    @classmethod
    def denied(
        cls,
        *,
        code: tls_certificates.CertificateRequestErrorCode = (
            tls_certificates.CertificateRequestErrorCode.OTHER
        ),
        message: str = _DEFAULT_DENIAL_MESSAGE,
        reason: str | None = None,
    ) -> Outcome:
        """An error instead of a certificate.

        The requirer library surfaces it through ``get_request_errors()`` and
        ``get_request_error()``, and emits ``certificate_denied``. Customise it with this
        method's own ``code``, ``message`` and ``reason`` arguments.

        Args:
            code: The error code the provider reports.
            message: The message it reports.
            reason: Optional further detail, carried in the error's ``reason`` field.
        """
        return cls(_Kind.DENIED, code=code, message=message, reason=reason)

    @classmethod
    def renewing(cls) -> Outcome:
        """A certificate far enough through its validity period to be due for renewal.

        On its next reconcile the requirer library's renewal safety net withdraws the
        request and replaces it with a fresh one. Answering *that* takes a second remote
        with the default outcome -- see :class:`RemoteProvider` for the pattern.

        This needs no agreement with the charm's ``renewal_relative_time``: the library caps
        the threshold it derives from that argument, so one back-dating covers every value a
        charm can legally pass.

        Note which of the library's two renewal routes this reaches. When the library stores
        a certificate it schedules a Juju secret expiry, and Juju's ``secret-expired`` drives
        the renewal; separately, a safety net re-checks every certificate on every reconcile,
        for when that event doesn't fire or doesn't complete. This reaches the safety net.
        Both routes withdraw the request and re-request, so the charm ends up in the same
        place; only the event that takes it there differs. To exercise the secret-expiry
        route, run the charm until it holds certificates and fire ``ctx.on.secret_expired``
        at the secret it created.
        """
        return _RENEWING

    @classmethod
    def expired(cls) -> Outcome:
        """A certificate whose whole validity period is in the past.

        Use this to test what a charm does when renewal has *failed* and it is left holding
        a dead certificate. The library will not rescue it: the safety net covers
        certificates approaching expiry and stops at expiry itself, so an expired
        certificate stays assigned and is never re-requested. Whether the charm keeps
        serving, goes blocked, or raises the alarm is the charm's own decision, and this is
        how to pin it down.
        """
        return _EXPIRED

    @classmethod
    def revoked(cls) -> Outcome:
        """A certificate published with the relation's ``revoked`` flag set.

        The requirer library removes the certificate's Juju secret on its next reconcile.
        """
        return _REVOKED

    @property
    def code(self) -> tls_certificates.CertificateRequestErrorCode | None:
        """The code the provider reports for a denied outcome.

        ``None`` for every other outcome.
        """
        return self._code

    @property
    def message(self) -> str | None:
        """The message the provider reports for a denied outcome.

        ``None`` for every other outcome.
        """
        return self._message

    @property
    def reason(self) -> str | None:
        """The further detail the provider reports for a denied outcome.

        ``None`` for every other outcome, and for a denied outcome constructed without one.
        """
        return self._reason

    def __repr__(self) -> str:
        if self._kind is not _Kind.DENIED:
            return f"Outcome.{self._kind.name.lower()}()"
        args: list[str] = []
        if (
            code := self._code
        ) is not None and code is not tls_certificates.CertificateRequestErrorCode.OTHER:
            args.append(f"code=CertificateRequestErrorCode.{code.name}")
        if self._message != _DEFAULT_DENIAL_MESSAGE:
            args.append(f"message={self._message!r}")
        if self._reason is not None:
            args.append(f"reason={self._reason!r}")
        return f"Outcome.denied({', '.join(args)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Outcome):
            return NotImplemented
        return (
            self._kind is other._kind
            and self._code == other._code
            and self._message == other._message
            and self._reason == other._reason
        )

    def __hash__(self) -> int:
        return hash((self._kind, self._code, self._message, self._reason))

    def _denial(self) -> tls_certificates.CertificateError | None:
        """This outcome's ``CertificateError``, or ``None`` if it isn't a denial. Not public.

        ``code`` and ``message`` are only ever ``None`` on a non-denied outcome, because
        :meth:`denied` defaults both, so the checks below narrow rather than validate.
        """
        code, message = self._code, self._message
        if self._kind is not _Kind.DENIED or code is None or message is None:
            return None
        return tls_certificates.CertificateError(
            code=code.value, name=code.name, message=message, reason=self._reason
        )


_ISSUED = Outcome(_Kind.ISSUED)
_RENEWING = Outcome(_Kind.RENEWING)
_EXPIRED = Outcome(_Kind.EXPIRED)
_REVOKED = Outcome(_Kind.REVOKED)


_OutcomeArg: typing.TypeAlias = (
    "Outcome | Callable[[tls_certificates.CertificateRequestAttributes], Outcome]"
)
_Scope: typing.TypeAlias = "typing.Literal[tls_certificates.Mode.APP, tls_certificates.Mode.UNIT]"
_RequestsByMode: typing.TypeAlias = (
    "Mapping[_Scope, Iterable[tls_certificates.CertificateRequestAttributes]]"
)


class _Remote:
    """Shared plumbing for the two remote classes. Not public.

    Only ``publish`` requires knowledge of the interface; ``integrate``, ``run_changed`` and
    ``get_relation`` are generic, and every ``charmlibs.interfaces`` testing package will
    implement them the same way. They live here so that this package writes them once. If
    they later move to a shared dependency or into ``ops.testing`` itself, nothing visible
    to a charm author changes -- see OP093.

    A plain class rather than a frozen dataclass, though OP093 suggests one and a dataclass
    would satisfy every property it asks for. A dataclass commits a library to a much larger
    API surface than it looks like: ``dataclasses.replace``, ``astuple``, ``asdict``,
    ``is_dataclass`` and ``__dataclass_fields__`` all become part of the contract, which
    makes even adding an optional argument or reordering the existing ones a breaking
    change. See "Don't use dataclasses in your library's public API" on the Charmhub forum.
    The properties OP093 specifies -- immutability, readable ``endpoint`` and
    ``remote_app_name``, a useful ``__repr__`` -- are provided explicitly instead, since the
    spec is of those properties rather than of the mechanism.
    """

    def __init__(self, endpoint: str, *, remote_app_name: str = "remote") -> None:
        self._endpoint = endpoint
        self._remote_app_name = remote_app_name

    @property
    def endpoint(self) -> str:
        """The charm's endpoint name for this relation."""
        return self._endpoint

    @property
    def remote_app_name(self) -> str:
        """The name of the simulated remote application."""
        return self._remote_app_name

    def _repr_args(self) -> list[str]:
        """Constructor arguments to show in ``__repr__``, defaults omitted. Extended below."""
        args = [repr(self._endpoint)]
        if self._remote_app_name != "remote":
            args.append(f"remote_app_name={self._remote_app_name!r}")
        return args

    def __repr__(self) -> str:
        """Return a constructor-like representation, omitting arguments left at default.

        Worth having because ``pytest`` derives parametrize IDs from it, and because it
        locates any error raised here when several remotes are in play -- so it stays short
        by showing only what the caller actually chose.
        """
        return f"{type(self).__name__}({', '.join(self._repr_args())})"

    def integrate(
        self,
        ctx: testing.Context[typing.Any],
        state: testing.State,
        *,
        end: _End = "received",
    ) -> testing.State:
        """Relate the charm to this remote, and carry the conversation as far as ``end``.

        Adds the relation to the state and executes the charm for the events Juju fires on
        ``juju integrate`` -- ``relation-created``, then ``relation-joined`` and
        ``relation-changed`` for the remote's single unit -- and then goes as far as ``end``
        says.

        A bare relation for this remote that is already in the state -- which is what
        ``ops.testing.State.from_context`` puts there for every endpoint in the charm's
        metadata -- is adopted rather than duplicated, since a relation with nothing written
        on it is exactly the starting point this method assumes. A relation that already has
        data on it means the conversation has already begun, and raises: carrying it on is
        what ``publish`` and ``run_changed`` are for.

        Args:
            ctx: The context for the charm under test. It is executed, and mutated as a
                result: ``ctx.run`` appends to ``ctx.emitted_events`` and the other
                accumulating attributes. Don't assume how many times, or that it happens at
                all; ``run_changed`` is the one method whose charm executions are specified.
            state: The state to add the relation to. Everything in it is preserved, except
                that the charm's own execution may of course change it.
            end: How far to carry the conversation:

                - ``"integrated"``: the relation made, and the charm having published
                  whatever it publishes on integration.
                - ``"published"``: the above, plus this remote's data on the wire, not yet
                  seen by the charm.
                - ``"received"`` (the default): the above, plus the charm having reconciled
                  against it -- the settled relation.

        Returns:
            A new ``ops.testing.State``.

        Raises:
            RuntimeError: If called outside a :func:`mocked` scope.
            ValueError: If this remote already has a relation in ``state``, if ``end`` isn't
                one of the three values, or if adding the relation would exceed what the
                library supports on one endpoint.
        """
        _require_mocked("integrate")
        if end not in ("integrated", "published", "received"):
            raise ValueError(f"end must be 'integrated', 'published' or 'received', not {end!r}.")
        existing = self._find_relation(state)
        if existing is not None and _has_data(existing):
            raise ValueError(
                f"{self} already has a relation in this state, and there is data on it, so "
                "the conversation has already begun. integrate() starts one. To carry an "
                "existing relation on, use publish() and run_changed(); to model a second "
                "application on the same endpoint, construct a second remote with a "
                "different remote_app_name."
            )
        if existing is not None:
            # A bare relation is exactly integrate()'s starting point, so adopt it rather
            # than duplicate it. ops.testing.State.from_context creates one per endpoint in
            # the charm's metadata, so this is the common path, not an edge case.
            relation = existing
        else:
            self._check_can_add(state)
            relation = testing.Relation(
                self.endpoint, interface=_INTERFACE_NAME, remote_app_name=self.remote_app_name
            )
            state = dataclasses.replace(state, relations={*state.relations, relation})
        state = ctx.run(ctx.on.relation_created(relation), state)
        relation = self.get_relation(state)
        state = ctx.run(ctx.on.relation_joined(relation, remote_unit=_UNIT_ID), state)
        relation = self.get_relation(state)
        state = ctx.run(ctx.on.relation_changed(relation, remote_unit=_UNIT_ID), state)
        if end == "integrated":
            return state
        state = self.publish(state)
        if end == "published":
            return state
        return self.run_changed(ctx, state)

    def publish(self, state: testing.State) -> testing.State:
        """Write this remote's data, and any other state it is responsible for.

        The charm is not executed. Implemented by the two subclasses; see
        :meth:`RemoteProvider.publish` and :meth:`RemoteRequirer.publish`.
        """
        raise NotImplementedError

    def run_changed(self, ctx: testing.Context[typing.Any], state: testing.State) -> testing.State:
        """Execute the charm for ``relation-changed`` on this remote's relation.

        Exactly equivalent to::

            ctx.run(
                ctx.on.relation_changed(remote.get_relation(state), remote_unit=0), state
            )

        It exists because that expression is long, is repeated, and requires the caller to
        re-fetch the relation after every step, since each new immutable state has a new
        relation object. ``remote_unit`` is passed explicitly because the remote has exactly
        one unit, with ID 0; leaving it out means the same thing, but makes ``ops.testing``
        warn that the scenario may be inconsistent.

        Args:
            ctx: The context for the charm under test.
            state: The state to run against.

        Returns:
            A new ``ops.testing.State``.

        Raises:
            RuntimeError: If called outside a :func:`mocked` scope.
            KeyError: If this remote has no relation in ``state``.
        """
        _require_mocked("run_changed")
        relation = self.get_relation(state)
        return ctx.run(ctx.on.relation_changed(relation, remote_unit=_UNIT_ID), state)

    def get_relation(self, state: testing.State) -> testing.Relation:
        """Return this remote's relation from ``state``.

        The escape hatch for every relation event the other methods don't cover --
        ``relation-departed``, ``relation-broken``, and anything else::

            relation = certs.get_relation(state)
            state_out = ctx.run(ctx.on.relation_broken(relation), state)

        Unlike the state-producing methods this does not require a :func:`mocked` scope,
        because assertions commonly run after the scope has closed.

        Args:
            state: The state to look in.

        Returns:
            The ``ops.testing.Relation`` for this remote's endpoint and application name.

        Raises:
            KeyError: If there is no such relation. ``ops.testing.State`` raises ``KeyError``
                for a missing relation, so this does too.
        """
        relation = self._find_relation(state)
        if relation is None:
            endpoints = sorted({r.endpoint for r in state.relations})
            raise KeyError(
                f"{self} has no relation in this state (relations on: {endpoints}). "
                "Call integrate() first, or check the endpoint and remote_app_name match "
                "the relation you built by hand."
            )
        return relation

    def _find_relation(self, state: testing.State) -> testing.Relation | None:
        """Return this remote's relation, or None. Raises if the state holds two of them."""
        matches = [
            relation
            for relation in state.relations
            if isinstance(relation, testing.Relation)
            and relation.endpoint == self.endpoint
            and relation.remote_app_name == self.remote_app_name
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(
                f"{self} matches {len(matches)} relations in this state. A remote stands for "
                "one application on one endpoint, so give each simulated application its own "
                "remote_app_name."
            )
        return matches[0]

    def _check_can_add(self, state: testing.State) -> None:
        """Raise if adding a relation for this remote isn't supported. Overridden below."""

    def _relation_for(self, method: str, state: testing.State) -> testing.Relation:
        """Fetch this remote's relation for a state-producing method, with a fitting error."""
        try:
            return self.get_relation(state)
        except KeyError as e:
            # A missing relation is not an absence of data -- it's an incoherent call, so
            # unlike an empty databag it must raise. ValueError rather than the KeyError
            # get_relation raises, because here the caller asked to write to a relation
            # that doesn't exist rather than to look one up.
            raise ValueError(
                f"{self}.{method}() needs a relation, and there isn't one in this state. "
                "Call integrate() first, or add a bare ops.testing.Relation for "
                f"endpoint={self.endpoint!r} with remote_app_name={self.remote_app_name!r}."
            ) from e

    def _warn_if_nothing_published(self, published: bool, state: testing.State) -> None:
        """Log a hint when an empty databag has a likely, but not certain, explanation."""
        if published or state.leader:
            return
        # Not raised, though OP093 allows a library to raise where it can name a specific
        # reason the charm published nothing. Non-leadership is a specific reason but not an
        # unambiguous one here: a Mode.UNIT requirer publishes as a non-leader perfectly
        # well, and a charm with no requests configured also publishes nothing. Raising
        # would obstruct a test that arranges this relation incidentally while being about
        # something else, which the spec explicitly protects.
        logger.warning(
            "%s.publish() found nothing to answer, and this state is not the leader. A "
            "requirer charm using Mode.APP or Mode.APP_AND_UNIT writes its requests to the "
            "application databag, which a non-leader unit cannot do -- so if that is the "
            "charm under test, pass leader=True to ops.testing.State.",
            self,
        )


class RemoteProvider(_Remote):
    """A simulated ``tls-certificates`` provider, for testing a **requirer** charm.

    The charm under test asks for certificates; this stands in for the application that
    issues them. Because the requirer writes first, the certificates are signed from the
    certificate signing requests the charm *actually published* -- never from a canned
    value. That is what makes the fixture impossible to silently disagree with: there is no
    request list to keep in step with the charm's, and no private key to seed, whether the
    charm lets the library manage its key or supplies its own.

    The happy path is one line::

        CERTS = tls_certificates_testing.RemoteProvider("certificates")

        def test_certificates(ctx: testing.Context):
            with tls_certificates_testing.mocked():
                state = CERTS.integrate(ctx, testing.State.from_context(ctx))
            assert isinstance(state.unit_status, testing.ActiveStatus)

    The requirer library reads its relation with ``Model.get_relation``, which raises when
    an endpoint carries more than one relation, so a charm under test can have only one
    provider per endpoint. Attempting a second raises ``ValueError``. Several *endpoints*
    are fine, one remote each.

    Args:
        endpoint: The charm's endpoint name for this relation.
        remote_app_name: The name of the simulated provider application.
        outcome: What the provider does with each request -- an :class:`Outcome` from one of
            its constructors, or a callable choosing one per request. Defaults to issuing a
            certificate for everything.
        capabilities: What the provider has advertised about its certificate server.
            ``None``, the default, models a provider that has not advertised anything, which
            ``get_provider_capabilities()`` reports as ``None`` ("not known yet"). Pass a
            ``ProviderCapabilities`` -- even an empty one -- to model a provider that has,
            with each field carrying its own three-way meaning per the library's docs.
        validity: How long issued certificates are valid for. Rarely worth changing:
            ``Outcome.renewing()`` and ``Outcome.expired()`` express the interesting
            positions within the validity period without needing a specific length.

    To complete a renewal, publish again with a remote whose outcome is the default. The
    remote is immutable and its results depend only on its arguments and the state, so two
    remotes for the same application are just two ways of answering::

        STALE = RemoteProvider("certificates", outcome=Outcome.renewing())
        FRESH = RemoteProvider("certificates")

        with tls_certificates_testing.mocked():
            # The charm holds a stale certificate, and its reconcile re-requests.
            state = STALE.integrate(ctx, testing.State.from_context(ctx))
            # The provider answers the fresh request properly.
            state = FRESH.publish(state)
            state_out = FRESH.run_changed(ctx, state)
    """

    def __init__(
        self,
        endpoint: str,
        *,
        remote_app_name: str = "remote",
        outcome: _OutcomeArg = _ISSUED,
        capabilities: tls_certificates.ProviderCapabilities | None = None,
        validity: datetime.timedelta = _DEFAULT_VALIDITY,
    ) -> None:
        super().__init__(endpoint, remote_app_name=remote_app_name)
        self._outcome = outcome
        self._capabilities = capabilities
        self._validity = validity

    @property
    def outcome(self) -> _OutcomeArg:
        """What the provider does with each request."""
        return self._outcome

    @property
    def capabilities(self) -> tls_certificates.ProviderCapabilities | None:
        """What the provider has advertised, or ``None`` if it has advertised nothing."""
        return self._capabilities

    @property
    def validity(self) -> datetime.timedelta:
        """How long issued certificates are valid for."""
        return self._validity

    def _repr_args(self) -> list[str]:
        args = super()._repr_args()
        if self._outcome != Outcome.issued():
            # Outcome's own __repr__ is self-describing, and a callable's own repr is still
            # the fallback -- so there is nothing left for this method to add.
            args.append(f"outcome={self._outcome!r}")
        if self._capabilities is not None:
            args.append(f"capabilities={self._capabilities!r}")
        if self._validity != _DEFAULT_VALIDITY:
            args.append(f"validity={self._validity!r}")
        return args

    def publish(self, state: testing.State) -> testing.State:
        """Write the provider's answer to whatever the charm has currently requested.

        Recomputes the provider's application databag from the charm's own relation data. A
        certificate (or error) is added for each request the provider hasn't answered;
        answers it has already published are kept as they are, including their back-dated or
        revoked state; and answers to requests the charm has since withdrawn are dropped,
        which is what the real provider library does too. The postcondition is "the
        provider's data is correct for this state", so calling it twice with nothing else
        changed leaves the state unchanged.

        Existing certificates are kept rather than re-signed because signing is
        non-deterministic -- a random serial number, and validity dates from the current
        clock -- and a databag that changed on every call would neither be idempotent nor
        let a test assert that a certificate had not been reissued.

        Where the charm has requested nothing, nothing is written and the state comes back
        unchanged, rather than raising: a test that arranges this relation incidentally,
        while being about something else, shouldn't be obstructed. A missing *relation* is
        different -- that's an incoherent call, and raises.

        Args:
            state: The state to write into. Only this remote's relation data is touched;
                other relations, other remotes on the same endpoint, and the rest of the
                state are preserved as they are.

        Returns:
            A new ``ops.testing.State``.

        Raises:
            RuntimeError: If called outside a :func:`mocked` scope.
            ValueError: If this remote has no relation in ``state``.
        """
        _require_mocked("publish")
        relation = self._relation_for("publish", state)
        requests = _load_requirer(relation.local_app_data, relation.local_unit_data)
        published = _load_provider(relation.remote_app_data)
        data = self._answer(requests, published)
        self._warn_if_nothing_published(bool(requests), state)
        return _replace_relation(state, relation, remote_app_data=_dump(data))

    def _answer(
        self,
        requests: list[_Request],
        published: _internal._ProviderApplicationData,
    ) -> _internal._ProviderApplicationData:
        """Return the provider's databag: what it still owes, plus what it already said."""
        wanted = {request.csr for request in requests}
        # Load-modify-dump: keep what the provider has already said about requests that are
        # still on the relation, and answer only the ones it hasn't.
        certificates = [
            certificate
            for certificate in published.certificates
            if _as_csr(certificate.certificate_signing_request) in wanted
        ]
        errors = [error for error in published.request_errors if _as_csr(error.csr) in wanted]
        answered = {_as_csr(c.certificate_signing_request) for c in certificates}
        answered |= {_as_csr(e.csr) for e in errors}
        for request in requests:
            if request.csr in answered:
                continue
            outcome = self._outcome_for(request)
            denial = outcome._denial()
            if denial is not None:
                errors.append(_internal._RequestError(csr=str(request.csr), error=denial))
                continue
            certificates.append(self._certificate_entry(request, outcome))
        return _internal._ProviderApplicationData(
            certificates=certificates, request_errors=errors, capabilities=self.capabilities
        )

    def _outcome_for(self, request: _Request) -> Outcome:
        if isinstance(self.outcome, Outcome):
            return self.outcome
        # Reconstruct what the charm asked for, so the callable selects on the request
        # rather than on the wire format.
        attributes = tls_certificates.CertificateRequestAttributes.from_csr(
            request.csr, is_ca=request.is_ca
        )
        outcome = self.outcome(attributes)
        if not isinstance(outcome, Outcome):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(
                f"The outcome callable returned {outcome!r}, not a "
                "tls_certificates_testing.Outcome."
            )
        return outcome

    def _certificate_entry(self, request: _Request, outcome: Outcome) -> _internal._Certificate:
        certificate = request.csr.sign(
            ca=_CA_CERT, ca_private_key=_CA_KEY, validity=self.validity, is_ca=request.is_ca
        )
        if outcome == Outcome.renewing():
            # The library validates 0.5 < renewal_relative_time <= 1.0 and caps the safety
            # net's threshold, so a certificate aged past that cap is due for renewal under
            # every value a charm can legally pass -- hence no argument here, and no
            # coupling for a caller to get silently wrong. The safety net renews from the
            # threshold through to expiry, so aiming halfway between the cap and expiry sits
            # comfortably inside the window. The cap comes from the library rather than a
            # copy of its value, so raising it there can't leave this quietly not renewing.
            age = (_internal._MAX_RENEWAL_FRACTION + 1.0) / 2
            certificate = _backdate(certificate, age=age, validity=self.validity)
        elif outcome == Outcome.expired():
            certificate = _backdate(certificate, age=1.5, validity=self.validity)
        return _internal._Certificate(
            certificate=str(certificate),
            certificate_signing_request=str(request.csr),
            ca=str(_CA_CERT),
            chain=[str(certificate), str(_CA_CERT)],  # leaf to root
            revoked=True if outcome == Outcome.revoked() else None,
        )

    def _check_can_add(self, state: testing.State) -> None:
        existing = [
            relation
            for relation in state.relations
            if isinstance(relation, testing.Relation) and relation.endpoint == self.endpoint
        ]
        if existing:
            others = sorted(r.remote_app_name for r in existing)
            raise ValueError(
                f"Endpoint {self.endpoint!r} already has a relation (to {others}), and the "
                "requirer library reads its relation with Model.get_relation, which raises "
                "when an endpoint carries more than one. A requirer charm can therefore be "
                "tested against only one provider per endpoint. Use a second endpoint, with "
                "its own remote, instead."
            )


class RemoteRequirer(_Remote):
    """A simulated ``tls-certificates`` requirer, for testing a **provider** charm.

    The charm under test issues certificates; this stands in for the application that asks
    for them. Here the remote writes first, so there is nothing to derive from the charm and
    the requests are supplied as ordinary fixture configuration::

        WORKLOAD = tls_certificates_testing.RemoteRequirer("certificates")

        def test_issues_certificates(ctx: testing.Context):
            with tls_certificates_testing.mocked():
                state = WORKLOAD.integrate(ctx, testing.State.from_context(ctx, leader=True))
            assert isinstance(state.unit_status, testing.ActiveStatus)

    Note ``leader=True``. ``TLSCertificatesProvidesV4`` writes to the application databag,
    so a non-leader provider charm answers nothing, which is invisible in the resulting
    state and easily mistaken for a bug in the charm.

    A provider charm may be related to several requirer applications on one endpoint, so
    several remotes on one endpoint are supported, one per application::

        WORKERS = [RemoteRequirer("certificates", remote_app_name=f"worker{n}") for n in range(3)]

    Args:
        endpoint: The charm's endpoint name for this relation.
        remote_app_name: The name of the simulated requirer application.
        certificate_requests: The requests the simulated requirer makes. Defaults to one
            request for ``example.com``. A request with ``is_ca=True`` asks for a CA
            certificate. Must not be given when ``mode`` is ``Mode.APP_AND_UNIT``.
        mode: Which databag the requests go in, mirroring the ``mode`` a real requirer would
            pass to ``TLSCertificatesRequiresV4``. ``Mode.UNIT`` (the default) uses the
            remote unit's databag, ``Mode.APP`` the remote application's, and
            ``Mode.APP_AND_UNIT`` splits them per ``certificate_requests_by_mode``.
        certificate_requests_by_mode: The requests per scope, mirroring
            ``TLSCertificatesRequiresV4(certificate_requests_by_mode=...)``. Required when
            ``mode`` is ``Mode.APP_AND_UNIT`` -- where it defaults to one application and
            one unit request -- and rejected otherwise.
        private_key: The key the simulated requirer signs its requests with. Free to choose;
            a provider charm never sees it, and ``TLSCertificatesProvidesV4`` manages no key
            of its own, so nothing needs seeding for the charm under test.

    Raises:
        ValueError: If ``certificate_requests`` and ``certificate_requests_by_mode`` aren't
            used in the combination ``mode`` requires. Mirrors the pairing rules the library
            enforces on a real requirer's own arguments, so a remote can't be built in a
            shape a real requirer could not have produced.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        remote_app_name: str = "remote",
        certificate_requests: (
            Iterable[tls_certificates.CertificateRequestAttributes] | None
        ) = None,
        mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
        certificate_requests_by_mode: _RequestsByMode | None = None,
        private_key: tls_certificates.PrivateKey = _DEFAULT_KEY,
    ) -> None:
        super().__init__(endpoint, remote_app_name=remote_app_name)
        # The iterables are consumed into tuples straight away, so that a remote really is
        # immutable and reusable across tests: a generator would otherwise be consumed by
        # the first call and empty for the second. Accepting an Iterable while exposing a
        # Sequence is one of the things a dataclass can't express.
        self._certificate_requests = (
            None if certificate_requests is None else tuple(certificate_requests)
        )
        self._mode = mode
        by_mode: dict[_Scope, tuple[tls_certificates.CertificateRequestAttributes, ...]] | None
        by_mode = (
            None
            if certificate_requests_by_mode is None
            else {
                scope: tuple(requests) for scope, requests in certificate_requests_by_mode.items()
            }
        )
        self._certificate_requests_by_mode = by_mode
        self._private_key = private_key
        # Validate here rather than on first use, so that a badly built remote fails at the
        # point it is written -- which for a module-level remote is at import.
        self._scopes  # noqa: B018

    @property
    def certificate_requests(
        self,
    ) -> Sequence[tls_certificates.CertificateRequestAttributes] | None:
        """The requests the simulated requirer makes, or ``None`` if split by mode."""
        return self._certificate_requests

    @property
    def mode(self) -> tls_certificates.Mode:
        """Which databag the requests go in."""
        return self._mode

    @property
    def certificate_requests_by_mode(
        self,
    ) -> Mapping[_Scope, Sequence[tls_certificates.CertificateRequestAttributes]] | None:
        """The requests per scope, or ``None`` unless ``mode`` is ``Mode.APP_AND_UNIT``."""
        return self._certificate_requests_by_mode

    @property
    def private_key(self) -> tls_certificates.PrivateKey:
        """The key the simulated requirer signs its requests with."""
        return self._private_key

    @property
    def _scopes(self) -> dict[_Scope, tuple[tls_certificates.CertificateRequestAttributes, ...]]:
        """This remote's requests keyed by scope, validating them. Cheap: already tuples."""
        return _requests_by_mode(
            self._mode, self._certificate_requests, self._certificate_requests_by_mode
        )

    def _repr_args(self) -> list[str]:
        args = super()._repr_args()
        if self._certificate_requests is not None:
            args.append(f"certificate_requests={list(self._certificate_requests)!r}")
        if self._mode is not tls_certificates.Mode.UNIT:
            args.append(f"mode=Mode.{self._mode.name}")
        if self._certificate_requests_by_mode is not None:
            by_mode = {
                f"Mode.{scope.name}": list(requests)
                for scope, requests in self._certificate_requests_by_mode.items()
            }
            args.append(f"certificate_requests_by_mode={by_mode!r}")
        if self._private_key != _DEFAULT_KEY:
            # Not the key itself: a PEM private key in a pytest parametrize ID is unreadable,
            # and printing key material in test output is a habit worth not forming.
            args.append("private_key=<custom>")
        return args

    def publish(self, state: testing.State) -> testing.State:
        """Write the simulated requirer's certificate requests.

        Recomputes the remote's databags from ``certificate_requests`` and ``mode``: a
        request is added for each one that isn't already on the relation, and anything on the
        relation that this remote no longer asks for is removed, which is what a real
        requirer's library does when its configuration changes. The postcondition is "the
        requirer's data is correct for this state", so calling it twice with nothing else
        changed leaves the state unchanged.

        Requests already on the relation are kept byte for byte rather than re-signed,
        because the library gives each request a unique subject identifier by default, so
        re-signing would produce a different certificate signing request each time. A
        provider charm would then see its issued certificates orphaned on every call.

        Only the remote's side is written, so the certificates the charm under test has
        issued are left alone -- letting a test change what the requirer asks for and watch
        the charm reconcile.

        Args:
            state: The state to write into. Only this remote's relation data is touched.

        Returns:
            A new ``ops.testing.State``.

        Raises:
            RuntimeError: If called outside a :func:`mocked` scope.
            ValueError: If this remote has no relation in ``state``.
        """
        _require_mocked("publish")
        relation = self._relation_for("publish", state)
        app = self._requests_for(tls_certificates.Mode.APP, existing=relation.remote_app_data)
        unit = self._requests_for(
            tls_certificates.Mode.UNIT, existing=relation.remote_units_data.get(_UNIT_ID, {})
        )
        units_data = {**relation.remote_units_data, _UNIT_ID: _dump(unit)}
        return _replace_relation(
            state, relation, remote_app_data=_dump(app), remote_units_data=units_data
        )

    def _requests_for(self, scope: _Scope, existing: Mapping[str, str]) -> _internal._RequirerData:
        """Return the databag model for one scope, reusing any request already published."""
        wanted = self._scopes.get(scope, ())
        published = {_attributes(entry): entry for entry in _load_requirer_data(existing).values()}
        entries: list[_internal._CertificateSigningRequest] = []
        for attributes in wanted:
            entry = published.get(attributes)
            if entry is None:
                csr = tls_certificates.CertificateSigningRequest.generate(
                    attributes=attributes, private_key=self._private_key
                )
                entry = _internal._CertificateSigningRequest(
                    certificate_signing_request=str(csr), ca=attributes.is_ca
                )
            entries.append(entry)
        return _internal._RequirerData(certificate_signing_requests=entries)


@dataclasses.dataclass(frozen=True)
class _Request:
    """A certificate request read off the wire: the signing request and its ``ca`` flag.

    A dataclass, unlike the public classes above: this one never leaves the package, so none
    of the compatibility surface a dataclass commits you to is exposed to anyone.
    """

    csr: tls_certificates.CertificateSigningRequest
    is_ca: bool


def _requests_by_mode(
    mode: tls_certificates.Mode,
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes] | None,
    certificate_requests_by_mode: _RequestsByMode | None,
) -> dict[_Scope, tuple[tls_certificates.CertificateRequestAttributes, ...]]:
    """Validate the request arguments against ``mode`` and return them keyed by scope."""
    app_and_unit = tls_certificates.Mode.APP_AND_UNIT
    if certificate_requests is not None and certificate_requests_by_mode is not None:
        raise ValueError(
            "certificate_requests and certificate_requests_by_mode are mutually exclusive."
        )
    if mode is app_and_unit:
        if certificate_requests is not None:
            raise ValueError(
                "certificate_requests must not be given when mode is Mode.APP_AND_UNIT; "
                "use certificate_requests_by_mode."
            )
        if certificate_requests_by_mode is None:
            certificate_requests_by_mode = {
                tls_certificates.Mode.APP: (_DEFAULT_APP_REQUEST,),
                tls_certificates.Mode.UNIT: (_DEFAULT_UNIT_REQUEST,),
            }
        # Iterate as plain Modes: the annotation rules APP_AND_UNIT out, but a caller
        # without a type checker can still pass it, and it must not reach the databag.
        keys = typing.cast("Iterable[tls_certificates.Mode]", certificate_requests_by_mode)
        invalid = sorted(m.name for m in keys if m is app_and_unit)
        if invalid:
            raise ValueError(
                "certificate_requests_by_mode keys must be Mode.APP or Mode.UNIT, "
                f"not {', '.join(invalid)}."
            )
        return {scope: tuple(requests) for scope, requests in certificate_requests_by_mode.items()}
    if certificate_requests_by_mode is not None:
        raise ValueError(
            "certificate_requests_by_mode is only valid when mode is Mode.APP_AND_UNIT; "
            "use certificate_requests."
        )
    if certificate_requests is None:
        certificate_requests = (_DEFAULT_REQUEST,)
    if mode is tls_certificates.Mode.APP:
        return {tls_certificates.Mode.APP: tuple(certificate_requests)}
    if mode is tls_certificates.Mode.UNIT:
        return {tls_certificates.Mode.UNIT: tuple(certificate_requests)}
    raise ValueError(f"mode must be Mode.UNIT, Mode.APP or Mode.APP_AND_UNIT, not {mode!r}.")


def _load_requirer(*databags: Mapping[str, str]) -> list[_Request]:
    """Return every certificate request across ``databags``, in the order they appear."""
    return [
        _Request(csr=_as_csr(entry.certificate_signing_request), is_ca=bool(entry.ca))
        for databag in databags
        for entry in _load_requirer_data(databag).values()
    ]


def _load_requirer_data(
    databag: Mapping[str, str],
) -> dict[str, _internal._CertificateSigningRequest]:
    """Load one requirer databag, keyed by signing request, treating bad data as empty."""
    if "certificate_signing_requests" not in databag:
        return {}
    try:
        data = _internal._RequirerData.load(databag)
    except tls_certificates.DataValidationError:
        # The library degrades the same way rather than raising, so a relation whose data
        # isn't valid interface data must still be answerable -- that's a state a test may
        # deliberately construct, and the point of the test is what the charm does with it.
        return {}
    return {
        entry.certificate_signing_request: entry for entry in data.certificate_signing_requests
    }


def _load_provider(databag: Mapping[str, str]) -> _internal._ProviderApplicationData:
    """Load the provider's application databag, treating unreadable data as empty."""
    try:
        return _internal._ProviderApplicationData.load(databag)
    except tls_certificates.DataValidationError:
        return _internal._ProviderApplicationData()


def _dump(data: _internal._DatabagModel) -> dict[str, str]:
    databag: dict[str, str] = {}
    data.dump(databag)
    return databag


def _has_data(relation: testing.Relation) -> bool:
    """Whether either side of ``relation`` carries interface data.

    Only the interface's own keys count. ``ops.testing`` pre-populates unit databags with
    Juju's network keys, so a relation that has never been written to is not empty.
    """
    keys = {"certificate_signing_requests", "certificates", "request_errors", "capabilities"}
    databags: list[Mapping[str, str]] = [
        relation.local_app_data,
        relation.local_unit_data,
        relation.remote_app_data,
        *relation.remote_units_data.values(),
    ]
    return any(keys & set(databag) for databag in databags)


def _as_csr(raw: str) -> tls_certificates.CertificateSigningRequest:
    """Parse a signing request, so databag entries compare by content not by whitespace."""
    return tls_certificates.CertificateSigningRequest.from_string(raw)


def _attributes(
    entry: _internal._CertificateSigningRequest,
) -> tls_certificates.CertificateRequestAttributes:
    """Return the attributes a databag entry was built from, for matching against wanted."""
    return tls_certificates.CertificateRequestAttributes.from_csr(
        _as_csr(entry.certificate_signing_request), is_ca=bool(entry.ca)
    )


def _replace_relation(
    state: testing.State,
    relation: testing.Relation,
    **changes: typing.Any,
) -> testing.State:
    """Return a copy of ``state`` with ``relation`` replaced, everything else preserved."""
    others = {r for r in state.relations if r.id != relation.id}
    return dataclasses.replace(
        state, relations={*others, dataclasses.replace(relation, **changes)}
    )


def _backdate(
    certificate: tls_certificates.Certificate,
    age: float,
    validity: datetime.timedelta,
) -> tls_certificates.Certificate:
    """Re-issue ``certificate`` with ``age`` of its validity period already elapsed.

    The library computes renewal as a fraction of ``expiry_time - validity_start_time``, and
    signing hardcodes ``not_valid_before`` to the time of issue, so aged certificates can
    only be built by hand: sign through the library as usual, keeping its extension
    handling, then rebuild the result with shifted validity dates and everything else copied
    verbatim, re-signed by the same testing CA.
    """
    cert = x509.load_pem_x509_certificate(str(certificate).encode())
    not_valid_before = datetime.datetime.now(datetime.timezone.utc) - validity * age
    builder = x509.CertificateBuilder(
        subject_name=cert.subject,
        issuer_name=cert.issuer,
        public_key=cert.public_key(),
        serial_number=cert.serial_number,
        not_valid_before=not_valid_before,
        not_valid_after=not_valid_before + validity,
    )
    for extension in cert.extensions:
        builder = builder.add_extension(extension.value, extension.critical)
    ca_key = serialization.load_pem_private_key(str(_CA_KEY).encode(), password=None)
    assert isinstance(ca_key, rsa.RSAPrivateKey)  # the testing CA is RSA
    backdated = builder.sign(ca_key, hashes.SHA256())
    return tls_certificates.Certificate.from_string(
        backdated.public_bytes(serialization.Encoding.PEM).decode()
    )
