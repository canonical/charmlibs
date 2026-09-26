# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The simulated remote applications: :class:`RemoteProvider` and :class:`RemoteRequirer`."""

from __future__ import annotations

import dataclasses
import json
import logging
import typing

from ops import testing

# The library's private module, for its databag models and the version its requirer
# advertises. Building relation data means writing the interface's wire format, which is
# private. Reusing it is deliberate -- this package and the library are released in lockstep
# and pin each other exactly, so they cannot drift, whereas a second copy of the wire format
# could. Every use is covered by a test.
from charmlibs.interfaces.certificate_transfer import _certificate_transfer as _internal

from . import _raw
from ._mocking import require_mocked as _require_mocked

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

logger = logging.getLogger(__name__)

_INTERFACE_NAME = 'certificate_transfer'
_UNIT_ID = 0
"""The simulated remote application's single unit. See the module docs on units."""

_DATABAG_KEYS = frozenset({'certificates', 'version', 'ca', 'certificate', 'chain'})
"""Every key either side of this interface writes, across both versions of it.

``certificates`` and ``version`` are the v1 provider's application databag; ``version``
alone is the requirer's; ``ca``, ``certificate``, ``chain`` and ``version`` are the v0
provider's unit databag.

Two jobs. ``integrate`` reads these to tell a relation that has never been written to from
one where the conversation has already begun: ``ops.testing`` pre-populates unit databags
with Juju's network keys, so an untouched relation is not empty. And ``publish`` treats them
as the keys this remote owns, so that recomputing its data leaves anything else in the
databag -- which only a test can have put there -- alone.
"""

_DEFAULT_CERTIFICATES: tuple[str, ...] = (_raw.CA_CERTS[0],)
"""What a provider transfers unless the test says otherwise: one CA certificate."""

_End: typing.TypeAlias = 'typing.Literal["integrated", "published", "received"]'
_Version: typing.TypeAlias = 'typing.Literal[0, 1]'

_V0: _Version = 0
_V1: _Version = 1
_VERSIONS = (_V0, _V1)
"""The two versions of this interface's wire format. See :data:`_DATABAG_KEYS`."""


class _Remote:
    """Shared plumbing for the two remote classes. Not public.

    Only ``publish`` requires knowledge of the interface; ``integrate``, ``run_changed`` and
    ``get_relation`` are generic, and every charmlibs.interfaces testing package implements
    them the same way. They live here so that this package writes them once. If they later
    move to a shared dependency or into ``ops.testing`` itself, nothing visible to a charm
    author changes.

    A plain class rather than a frozen dataclass, though a dataclass would satisfy every
    property required of a remote. A dataclass commits a library to a much larger API
    surface than it looks like: ``dataclasses.replace``, ``astuple``, ``asdict``,
    ``is_dataclass`` and ``__dataclass_fields__`` all become part of the contract, which
    makes even adding an optional argument or reordering the existing ones a breaking
    change. The required properties -- immutability, readable ``endpoint`` and
    ``remote_app_name``, a useful ``__repr__`` -- are provided explicitly instead.
    """

    def __init__(self, endpoint: str, *, remote_app_name: str = 'remote') -> None:
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
        """Constructor arguments to show in ``__repr__``, defaults omitted."""
        args = [repr(self._endpoint)]
        if self._remote_app_name != 'remote':
            args.append(f'remote_app_name={self._remote_app_name!r}')
        return args

    def __repr__(self) -> str:
        """Return a constructor-like representation, omitting arguments left at default.

        Worth having because ``pytest`` derives parametrize IDs from it, and because it
        locates any error raised here when several remotes are in play -- so it stays short
        by showing only what the caller actually chose.
        """
        return f'{type(self).__name__}({", ".join(self._repr_args())})'

    def integrate(
        self,
        ctx: testing.Context[typing.Any],
        state: testing.State,
        *,
        end: _End = 'received',
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
            ValueError: If this remote already has a relation with data on it in ``state``,
                or if ``end`` isn't one of the three values.
        """
        _require_mocked('integrate')
        if end not in ('integrated', 'published', 'received'):
            raise ValueError(f'end must be "integrated", "published" or "received", not {end!r}.')
        existing = self._find_relation(state)
        if existing is not None and _has_data(existing):
            raise ValueError(
                f'{self} already has a relation in this state, and there is data on it, so '
                'the conversation has already begun. integrate() starts one. To carry an '
                'existing relation on, use publish() and run_changed(); to model a second '
                'application on the same endpoint, construct a second remote with a '
                'different remote_app_name.'
            )
        if existing is not None:
            # A bare relation is exactly integrate()'s starting point, so adopt it rather
            # than duplicate it. ops.testing.State.from_context creates one per endpoint in
            # the charm's metadata, so this is the common path, not an edge case.
            relation = existing
        else:
            relation = testing.Relation(
                self.endpoint, interface=_INTERFACE_NAME, remote_app_name=self.remote_app_name
            )
            state = dataclasses.replace(state, relations={*state.relations, relation})
        state = ctx.run(ctx.on.relation_created(relation), state)
        relation = self.get_relation(state)
        state = ctx.run(ctx.on.relation_joined(relation, remote_unit=_UNIT_ID), state)
        relation = self.get_relation(state)
        state = ctx.run(ctx.on.relation_changed(relation, remote_unit=_UNIT_ID), state)
        if end == 'integrated':
            return state
        state = self.publish(state)
        if end == 'published':
            return state
        return self.run_changed(ctx, state)

    def publish(self, state: testing.State) -> testing.State:
        """Write this remote's data, and any other state it is responsible for.

        Implemented by the two subclasses; the only method that needs to know the interface.
        See :meth:`RemoteProvider.publish` and :meth:`RemoteRequirer.publish`.
        """
        raise NotImplementedError

    def run_changed(self, ctx: testing.Context[typing.Any], state: testing.State) -> testing.State:
        """Execute the charm for ``relation-changed`` on this remote's relation.

        Exactly equivalent to::

            ctx.run(ctx.on.relation_changed(remote.get_relation(state), remote_unit=0), state)

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
        _require_mocked('run_changed')
        relation = self.get_relation(state)
        return ctx.run(ctx.on.relation_changed(relation, remote_unit=_UNIT_ID), state)

    def get_relation(self, state: testing.State) -> testing.Relation:
        """Return this remote's relation from ``state``.

        The escape hatch for every relation event the other methods don't cover --
        ``relation-departed``, ``relation-broken``, and anything else::

            relation = remote.get_relation(state)
            state_out = ctx.run(ctx.on.relation_broken(relation), state)

        Unlike the state-producing methods this does not require a :func:`mocked` scope,
        because assertions commonly run after the scope has closed.

        Args:
            state: The state to look in.

        Returns:
            The ``ops.testing.Relation`` for this remote's endpoint and application name.

        Raises:
            KeyError: If there is no such relation. ``ops.testing.State`` raises
                ``KeyError`` for a missing relation, so this does too.
        """
        relation = self._find_relation(state)
        if relation is None:
            endpoints = sorted({r.endpoint for r in state.relations})
            raise KeyError(
                f'{self} has no relation in this state (relations on: {endpoints}). '
                'Call integrate() first, or check the endpoint and remote_app_name match '
                'the relation you built by hand.'
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
                f'{self} matches {len(matches)} relations in this state. A remote stands '
                'for one application on one endpoint, so give each simulated application '
                'its own remote_app_name.'
            )
        return matches[0]

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
                'Call integrate() first, or add a bare ops.testing.Relation for '
                f'endpoint={self.endpoint!r} with remote_app_name={self.remote_app_name!r}.'
            ) from e


class RemoteProvider(_Remote):
    """A simulated ``certificate_transfer`` provider, for testing a **requirer** charm.

    The charm under test receives CA certificates; this stands in for the application that
    hands them over. The certificates themselves are the remote's to choose, because the
    requirer asks for nothing in particular -- but *which version of the wire format they
    are written in* is derived from what the charm published, because that is the one thing
    the requirer does say, and because it is what the real provider library decides from.

    The happy path is one line::

        CA_CERTS = certificate_transfer_testing.RemoteProvider('certificates')

        def test_the_happy_path(ctx: testing.Context):
            with certificate_transfer_testing.mocked():
                state = CA_CERTS.integrate(ctx, testing.State.from_context(ctx, leader=True))
            assert isinstance(state.unit_status, testing.ActiveStatus)

    Note ``leader=True``. ``CertificateTransferRequires`` writes ``version: 1`` to its
    application databag on ``relation-created``, which a non-leader unit cannot do, so a
    non-leader requirer is indistinguishable from an old v0 one and is answered in the v0
    format. That still works -- the library reads v0 as a fallback -- but the relation data
    looks nothing like the v1 case, so it is worth knowing which one a test has arranged.

    One thing to know about the v0 format if a test lands on it. The library reads those
    certificates out of the provider's *unit* databag, and ``get_all_certificates`` takes the
    remote unit out of ``ops``' cached ``relation.units`` as it goes, so a charm that calls it
    twice in one hook reads nothing the second time. A charm that uses the
    ``certificate_set_updated`` event's own ``certificates``, as the library's docstring
    shows, never sees this.

    A requirer charm aggregates the certificates from every relation on the endpoint, so
    several remotes on one endpoint are supported, one per application::

        ISSUERS = [
            RemoteProvider('certificates', remote_app_name=name, certificates=[pem])
            for name, pem in (('root-ca', ROOT_PEM), ('intermediate-ca', INTERMEDIATE_PEM))
        ]

    Args:
        endpoint: The charm's endpoint name for this relation.
        remote_app_name: The name of the simulated provider application.
        certificates: The CA certificates this provider transfers, as PEM strings. Defaults
            to a single self-signed CA certificate, generated once and shipped with this
            package, valid for a hundred years so that a test never starts failing on a
            date. The interface treats these as opaque, so anything a charm under test can
            make sense of will do, including a deliberately malformed string. Pass an empty
            collection to model a provider that has nothing to transfer yet: in the v1
            format that is an answer, and it is an empty one; in v0 it is nothing at all,
            because v0 has no way to say "none".
        interface_version: Which version of the wire format to answer in. ``None``, the
            default, decides the way the real provider library does: v1 if the charm under
            test advertised ``version: 1``, and v0 otherwise. Pass ``1`` or ``0`` to force
            it -- ``0`` being how a test models an old provider charm talking to a modern
            requirer, which is the case the library's v0 fallback exists for and which
            cannot otherwise be reached from a leader charm.

    Raises:
        ValueError: If ``interface_version`` is neither ``None``, ``0`` nor ``1``.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        remote_app_name: str = 'remote',
        certificates: Iterable[str] | None = None,
        interface_version: _Version | None = None,
    ) -> None:
        super().__init__(endpoint, remote_app_name=remote_app_name)
        self._certificates = _DEFAULT_CERTIFICATES if certificates is None else tuple(certificates)
        _check_version(interface_version, allow_none=True)
        # Annotated because pyright widens a literal it infers from a parameter's value.
        self._interface_version: _Version | None = interface_version

    @property
    def certificates(self) -> tuple[str, ...]:
        """The CA certificates this provider transfers."""
        return self._certificates

    @property
    def interface_version(self) -> _Version | None:
        """The wire format to answer in, or ``None`` to decide from the charm's own data."""
        return self._interface_version

    def _repr_args(self) -> list[str]:
        args = super()._repr_args()
        if self._certificates != _DEFAULT_CERTIFICATES:
            # A count rather than the PEMs themselves: a certificate is over a kilobyte, and
            # this ends up in pytest's parametrize IDs and in error messages. So this one
            # argument makes the repr descriptive rather than constructor-like.
            args.append(f'certificates=<{len(self._certificates)}>')
        if self._interface_version is not None:
            args.append(f'interface_version={self._interface_version!r}')
        return args

    def publish(self, state: testing.State) -> testing.State:
        """Write the provider's certificates, in the format the charm under test asked for.

        Recomputes this remote's databags from scratch, so the postcondition is "the
        provider's data is correct for this state", not "certificates have been added".
        Calling it twice with nothing else changed leaves the state unchanged, and a
        certificate this remote no longer transfers is gone from the wire rather than left
        behind -- which is more than the real provider's ``add_certificates`` does on its
        own, but exactly what a provider charm that reconciles does.

        Which of the interface's two wire formats is used is derived from the charm's own
        relation data, the way ``CertificateTransferProvides`` decides it: v1, an application
        databag holding the certificate set, if the charm advertised ``version: 1``, and v0,
        a unit databag holding ``ca``, ``certificate`` and ``chain``, if it did not. Passing
        ``interface_version`` to the constructor overrides that. Switching between the two
        clears the other format's keys, so the state never holds both halves of the
        conversation at once.

        Unlike a request-response interface's provider, this one never waits: a
        ``certificate_transfer`` provider publishes what it has as soon as the relation
        exists, so ``publish`` always writes something, even on a relation the charm has not
        yet run against. The one exception is a provider with no certificates in the v0
        format, which has no way to say "none" -- v0's ``ca`` and ``certificate`` are single
        required strings -- and so writes nothing, as the real library does.

        The charm is not executed.

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
        _require_mocked('publish')
        relation = self._relation_for('publish', state)
        version = self._version_for(relation)
        app_payload = self._app_databag(version)
        unit_payload = self._unit_databag(version)
        units_data = {
            unit_id: dict(databag) for unit_id, databag in relation.remote_units_data.items()
        }
        units_data[_UNIT_ID] = {
            **_foreign_keys(units_data.get(_UNIT_ID, {})),
            **unit_payload,
        }
        return _replace_relation(
            state,
            relation,
            remote_app_data={**_foreign_keys(relation.remote_app_data), **app_payload},
            remote_units_data=units_data,
        )

    def _version_for(self, relation: testing.Relation) -> _Version:
        """The wire format to answer in: forced, or derived from what the charm published."""
        if self._interface_version is not None:
            return self._interface_version
        # CertificateTransferProvides._set_relation_data reads the requirer's application
        # databag exactly like this, defaulting to v0 where the key is absent. Note that the
        # value is the raw databag string rather than the parsed model: the requirer writes
        # it with json.dumps, so v1 is the two characters `"1"` minus the quotes.
        if relation.local_app_data.get('version', '0') == '1':
            return _V1
        logger.info(
            '%s.publish() is answering in the v0 format, because the charm under test has '
            'not advertised version 1 on this relation. CertificateTransferRequires writes '
            'that on relation-created, from the leader unit only, so pass leader=True to '
            'ops.testing.State if a modern requirer charm is under test. Pass '
            'interface_version=0 to say the v0 format was what you wanted.',
            self,
        )
        return _V0

    def _app_databag(self, version: _Version) -> dict[str, str]:
        """The provider's application databag for this format: v1 writes it, v0 doesn't."""
        if version == _V0:
            return {}
        data = _internal.ProviderApplicationData(certificates=set(self._certificates))
        databag = _dump(data)
        # The model's field is a set, so pydantic renders it in the set's iteration order,
        # which differs between interpreter runs. The requirer reads it straight back into a
        # set, so the order means nothing to a charm -- sorting it only keeps the bytes on
        # the wire the same from one run of a test to the next.
        databag['certificates'] = json.dumps(sorted(set(self._certificates)))
        return databag

    def _unit_databag(self, version: _Version) -> dict[str, str]:
        """The provider's unit databag for this format: v0 writes it, v1 doesn't."""
        if version == _V1 or not self._certificates:
            # v0 has no way to say "no certificates" -- `ca` and `certificate` are single
            # required strings -- so the real library writes nothing at all in that case.
            return {}
        chain = sorted(set(self._certificates))
        # The real library picks `list(data)[0]` out of a set for both `ca` and
        # `certificate`, which is to say an arbitrary one. Sorted, so it's the same one every
        # run; the requirer reads `chain` and ignores the other two either way.
        data = _internal.ProviderUnitDataV0(ca=chain[0], certificate=chain[0], chain=chain)
        return _dump(data)


class RemoteRequirer(_Remote):
    """A simulated ``certificate_transfer`` requirer, for testing a **provider** charm.

    The charm under test hands over CA certificates; this stands in for the application that
    receives them. A requirer says only one thing on this interface -- the version of the
    wire format it understands -- and it says it first, so there is nothing to derive from
    the charm and the request is ordinary fixture configuration::

        CLIENT = certificate_transfer_testing.RemoteRequirer('send-ca-cert')

        def test_transfers_its_ca(ctx: testing.Context):
            with certificate_transfer_testing.mocked():
                state = CLIENT.integrate(ctx, testing.State.from_context(ctx, leader=True))
            assert isinstance(state.unit_status, testing.ActiveStatus)

    Note ``leader=True``. ``CertificateTransferProvides`` logs a warning and does nothing for
    a non-leader unit, so a non-leader provider charm transfers nothing.

    Beware the order within ``integrate``, which is Juju's order and not the one a provider
    charm's author tends to picture. The charm runs for ``relation-created``,
    ``relation-joined`` and ``relation-changed`` *before* this remote's ``version`` reaches
    the wire, exactly as a provider in a real model may be joined before the requirer's
    application data has propagated. A provider charm that transfers certificates on
    ``relation-joined`` therefore writes them in the v0 format first, and rewrites them in
    v1 on the ``relation-changed`` that ``end="received"`` runs. That is faithful, and it is
    why ``end="integrated"`` is the state to assert on for "nobody has said anything yet".

    A provider charm transfers to every relation on the endpoint, so several remotes on one
    endpoint are supported, one per application::

        CLIENTS = [RemoteRequirer('send-ca-cert', remote_app_name=f'app{n}') for n in range(2)]

    Args:
        endpoint: The charm's endpoint name for this relation.
        remote_app_name: The name of the simulated requirer application.
        interface_version: The version of the wire format this requirer advertises.
            ``1``, the default, is what ``CertificateTransferRequires`` writes. Pass ``0`` to
            model an old requirer charm, which advertises nothing at all and so is answered
            in the v0 format -- for a v0 requirer, ``publish`` writes nothing.

    Raises:
        ValueError: If ``interface_version`` is neither ``0`` nor ``1``.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        remote_app_name: str = 'remote',
        interface_version: _Version = _V1,
    ) -> None:
        super().__init__(endpoint, remote_app_name=remote_app_name)
        _check_version(interface_version, allow_none=False)
        # Annotated because pyright widens a literal it infers from a parameter's value.
        self._interface_version: _Version = interface_version

    @property
    def interface_version(self) -> _Version:
        """The version of the wire format this requirer advertises."""
        return self._interface_version

    def _repr_args(self) -> list[str]:
        args = super()._repr_args()
        if self._interface_version != _V1:
            args.append(f'interface_version={self._interface_version!r}')
        return args

    def publish(self, state: testing.State) -> testing.State:
        """Write the version this requirer advertises to its application databag.

        Recomputes the remote's application databag, so the postcondition is "the requirer's
        data is correct for this state". It follows that calling it twice with nothing else
        changed leaves the state unchanged, and that switching a remote from v1 to v0 clears
        the key rather than leaving it behind.

        A v0 requirer advertises nothing -- an absent ``version`` key *is* how v0 is spelled
        -- so ``publish`` writes nothing for one and returns the state unchanged. That is a
        remote that would not write, not a failure, and the provider charm under test reads
        it exactly as it reads a real v0 requirer: as a reason to fall back to the v0 format.

        Only the remote's side is written, so the certificates the charm under test has
        published are left alone. ``certificate_transfer`` requirers write to the application
        databag only, so the remote's unit databag is left as Juju leaves it.

        The charm is not executed.

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
        _require_mocked('publish')
        relation = self._relation_for('publish', state)
        payload = (
            {} if self._interface_version == _V0 else _dump(_internal.RequirerApplicationData())
        )
        return _replace_relation(
            state,
            relation,
            remote_app_data={**_foreign_keys(relation.remote_app_data), **payload},
        )


def _check_version(version: object, *, allow_none: bool) -> None:
    """Raise early where interface_version isn't a version of this interface.

    Checks rather than returns, so that the caller assigns the value it was given and the
    attribute keeps its declared type.
    """
    if version in _VERSIONS or (version is None and allow_none):
        return
    allowed = 'None, 0 or 1' if allow_none else '0 or 1'
    raise ValueError(
        f'interface_version={version!r} is not a version of the certificate_transfer '
        f'interface. Pass {allowed}.'
    )


def _dump(data: _internal.DatabagModel) -> dict[str, str]:
    """Render a databag model to the wire, through the library's own serialisation."""
    databag: dict[str, str] = {}
    # dump writes into the mapping it is given, and also returns it; the mapping is typed
    # here even though the library's own signature -- a bare MutableMapping[str, Any] -- isn't.
    data.dump(databag)
    return databag


def _foreign_keys(databag: Mapping[str, str]) -> dict[str, str]:
    """The part of a databag this remote doesn't own, which recomputing must preserve.

    Juju's own network keys in a unit databag, and anything a test put there deliberately.
    """
    return {key: value for key, value in databag.items() if key not in _DATABAG_KEYS}


def _has_data(relation: testing.Relation) -> bool:
    """Whether either side of ``relation`` carries interface data.

    Only the interface's own keys count. ``ops.testing`` pre-populates unit databags with
    Juju's network keys, so a relation that has never been written to is not empty.
    """
    databags: list[Mapping[str, str]] = [
        relation.local_app_data,
        relation.local_unit_data,
        relation.remote_app_data,
        *relation.remote_units_data.values(),
    ]
    return any(_DATABAG_KEYS & set(databag) for databag in databags)


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
