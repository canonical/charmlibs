# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The simulated remote applications: :class:`RemoteProvider` and :class:`RemoteRequirer`."""

from __future__ import annotations

import dataclasses
import json
import logging
import typing

import pydantic
from ops import testing

# The library's databag models, and the mapping from a protocol to its transport. Building
# relation data means writing the interface's wire format, and reusing the library's own
# models for it is deliberate -- this package and the library are released in lockstep and
# pin each other exactly, so they cannot drift, whereas a second copy of the wire format
# could. Every use is covered by a test.
from charmlibs.interfaces import tracing

from ._mocking import require_mocked as _require_mocked

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

logger = logging.getLogger(__name__)

_INTERFACE_NAME = 'tracing'
_UNIT_ID = 0
"""The simulated remote application's single unit. See the module docs on units."""

_DATABAG_KEYS = frozenset({'receivers'})
"""The databag keys this interface uses -- the same key on both sides.

``integrate`` reads these to tell a relation that has never been written to from one where
the conversation has already begun: ``ops.testing`` pre-populates unit databags with Juju's
network keys, so an untouched relation is not empty.
"""

_PORTS: dict[tracing.ReceiverProtocol, int] = {
    'jaeger_grpc': 14250,
    'jaeger_thrift_http': 14268,
    'otlp_grpc': 4317,
    'otlp_http': 4318,
    'zipkin': 9411,
}
"""The port the simulated provider serves each protocol on: each protocol's usual one."""

_DEFAULT_HOST = 'tracing.example.com'
_DEFAULT_PROTOCOLS: tuple[tracing.ReceiverProtocol, ...] = ('otlp_http',)

_End: typing.TypeAlias = 'typing.Literal["integrated", "published", "received"]'


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
    """A simulated ``tracing`` provider, for testing a **requirer** charm.

    The charm under test asks for protocols to send traces with; this stands in for the
    application that serves them. Because the requirer writes first, the receivers are
    derived from the protocols the charm *actually requested* -- never from a canned list.
    That is what makes the fixture impossible to silently disagree with: there is no list of
    protocols to keep in step with the charm's own.

    The happy path is one line::

        TRACING = tracing_testing.RemoteProvider('tracing')

        def test_the_happy_path(ctx: testing.Context):
            with tracing_testing.mocked():
                state = TRACING.integrate(ctx, testing.State.from_context(ctx, leader=True))
            assert isinstance(state.unit_status, testing.ActiveStatus)

    Note ``leader=True``. ``TracingEndpointRequirer`` publishes its request to the
    application databag, so a non-leader requirer charm asks for nothing, there is nothing
    to answer, and the settled state has an empty relation -- which is easily mistaken for a
    bug in the charm. ``publish`` logs a warning when it sees that combination.

    A requirer charm may be related to several tracing providers on one endpoint, if its
    metadata doesn't set ``limit: 1``, so several remotes on one endpoint are supported, one
    per application::

        BACKENDS = [RemoteProvider('tracing', remote_app_name=f'tempo{n}') for n in range(2)]

    Args:
        endpoint: The charm's endpoint name for this relation.
        remote_app_name: The name of the simulated provider application.
        supported_protocols: The protocols this provider serves. ``None``, the default,
            means it serves every protocol the charm requests, which is the happy path. Pass
            a subset to model a provider that doesn't support everything asked of it -- it
            answers with the protocols it has, omitting the rest, exactly as a real provider
            does. Pass an empty collection to model one that supports none of them, which
            still publishes an answer, just an empty one.
        host: The host the receiver URLs point at. Each protocol is served on its usual
            port: 4317 for ``otlp_grpc``, 4318 for ``otlp_http``, 9411 for ``zipkin``,
            14250 for ``jaeger_grpc`` and 14268 for ``jaeger_thrift_http``.
        tls: Whether the provider is behind TLS, making the URLs of the HTTP protocols
            ``https://`` rather than ``http://``. gRPC URLs carry no scheme either way, as
            the interface requires, so this is invisible to a charm that requests only gRPC
            protocols.

    Raises:
        ValueError: If ``supported_protocols`` names something that isn't a protocol of
            this interface.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        remote_app_name: str = 'remote',
        supported_protocols: Iterable[tracing.ReceiverProtocol] | None = None,
        host: str = _DEFAULT_HOST,
        tls: bool = False,
    ) -> None:
        super().__init__(endpoint, remote_app_name=remote_app_name)
        self._supported_protocols = (
            None if supported_protocols is None else tuple(supported_protocols)
        )
        if self._supported_protocols is not None:
            _check_protocols(self._supported_protocols, 'supported_protocols')
        self._host = host
        self._tls = tls

    @property
    def supported_protocols(self) -> tuple[tracing.ReceiverProtocol, ...] | None:
        """The protocols this provider serves, or ``None`` if it serves whatever is asked."""
        return self._supported_protocols

    @property
    def host(self) -> str:
        """The host the receiver URLs point at."""
        return self._host

    @property
    def tls(self) -> bool:
        """Whether the HTTP receiver URLs are ``https://``."""
        return self._tls

    def _repr_args(self) -> list[str]:
        args = super()._repr_args()
        if self._supported_protocols is not None:
            args.append(f'supported_protocols={self._supported_protocols!r}')
        if self._host != _DEFAULT_HOST:
            args.append(f'host={self._host!r}')
        if self._tls:
            args.append(f'tls={self._tls!r}')
        return args

    def publish(self, state: testing.State) -> testing.State:
        """Write the provider's answer to whatever the charm has currently requested.

        Recomputes the provider's application databag from the charm's own relation data: a
        receiver is written for each protocol the charm has requested and this provider
        supports, and requested protocols it doesn't support are omitted, which is what a
        real provider does. The postcondition is "the provider's data is correct for this
        state", not "an answer has been appended", so calling it twice with nothing else
        changed leaves the state unchanged, and a protocol the charm has stopped asking for
        disappears from the answer.

        Where the charm has requested nothing -- because it has not run yet, because it
        requests no protocols, or because it is not the leader and so cannot write to its
        application databag -- nothing is written and the state comes back unchanged, rather
        than raising: a test that arranges this relation incidentally, while being about
        something else, shouldn't be obstructed. A missing *relation* is different -- that's
        an incoherent call, and raises.

        Note the distinction from a charm that requests protocols this provider doesn't
        support. That is an answer, just an empty one, so an empty receiver list is written.
        A requirer charm can tell the two apart: ``is_ready`` is false where nothing was
        published and true where an empty list was.

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
        requested = _requested_protocols(relation.local_app_data)
        if requested is None:
            self._warn_if_nothing_requested(state)
            return state
        receivers = [self._receiver(protocol) for protocol in requested if self._serves(protocol)]
        return _replace_relation(
            state,
            relation,
            remote_app_data=_dump(tracing.TracingProviderAppData(receivers=receivers)),
        )

    def _serves(self, protocol: str) -> bool:
        """Whether this provider answers a requested protocol with a receiver."""
        if protocol not in _PORTS:
            # A protocol the interface doesn't define. A real provider can only omit it, so
            # that is what this does -- the requirer's own library logs the resulting
            # absence when the charm asks for the endpoint.
            logger.debug('%s: no receiver for unknown protocol %r.', self, protocol)
            return False
        if self._supported_protocols is None:
            return True
        return protocol in self._supported_protocols

    def _receiver(self, protocol: tracing.ReceiverProtocol) -> tracing.Receiver:
        """Build the receiver this provider advertises for one protocol."""
        transport = tracing.receiver_protocol_to_transport_protocol[protocol]
        return tracing.Receiver(
            protocol=tracing.ProtocolType(name=protocol, type=transport),
            url=self._url(protocol, transport),
        )

    def _url(
        self, protocol: tracing.ReceiverProtocol, transport: tracing.TransportProtocolType
    ) -> str:
        """The URL for one protocol: no scheme for gRPC, as the interface requires."""
        port = _PORTS[protocol]
        if transport is tracing.TransportProtocolType.grpc:
            return f'{self._host}:{port}'
        return f'{"https" if self._tls else "http"}://{self._host}:{port}'

    def _warn_if_nothing_requested(self, state: testing.State) -> None:
        """Log a hint when an empty databag has a likely, but not certain, explanation."""
        if state.leader:
            return
        # Not raised, though OP093 allows a library to raise where it can name a specific
        # reason the charm published nothing. Non-leadership is a specific reason but not an
        # unambiguous one: a charm that requests no protocols also publishes nothing, and a
        # charm that hasn't run yet hasn't either. Raising would obstruct a test that
        # arranges this relation incidentally while being about something else, which the
        # spec explicitly protects.
        logger.warning(
            '%s.publish() found no requested protocols, and this state is not the leader. '
            'TracingEndpointRequirer writes its request to the application databag, which a '
            'non-leader unit cannot do -- so if a requirer charm is under test, pass '
            'leader=True to ops.testing.State.',
            self,
        )


class RemoteRequirer(_Remote):
    """A simulated ``tracing`` requirer, for testing a **provider** charm.

    The charm under test serves tracing endpoints; this stands in for the application that
    asks for them. Here the remote writes first, so there is nothing to derive from the
    charm and the request is supplied as ordinary fixture configuration::

        WORKLOAD = tracing_testing.RemoteRequirer('tracing')

        def test_serves_endpoints(ctx: testing.Context):
            with tracing_testing.mocked():
                state = WORKLOAD.integrate(ctx, testing.State.from_context(ctx, leader=True))
            assert isinstance(state.unit_status, testing.ActiveStatus)

    Note ``leader=True``. ``TracingEndpointProvider.publish_receivers`` raises for a
    non-leader unit, so a provider charm that answers unconditionally errors out.

    A provider charm aggregates the protocols requested across every relation on the
    endpoint, so several remotes on one endpoint are supported, one per application::

        WORKLOADS = [
            RemoteRequirer('tracing', remote_app_name=f'app{n}', protocols=[p])
            for n, p in enumerate(('otlp_http', 'otlp_grpc'))
        ]

    Args:
        endpoint: The charm's endpoint name for this relation.
        remote_app_name: The name of the simulated requirer application.
        protocols: The protocols this requirer asks to send traces with. Defaults to
            ``otlp_http`` alone.

    Raises:
        ValueError: If ``protocols`` is empty, or names something that isn't a protocol of
            this interface. The library refuses an empty request too: a requirer that wants
            nothing doesn't write, which is a bare relation rather than a published one.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        remote_app_name: str = 'remote',
        protocols: Sequence[tracing.ReceiverProtocol] = _DEFAULT_PROTOCOLS,
    ) -> None:
        super().__init__(endpoint, remote_app_name=remote_app_name)
        self._protocols = tuple(protocols)
        if not self._protocols:
            raise ValueError(
                f'{type(self).__name__} needs at least one protocol to request. '
                'TracingEndpointRequirer.request_protocols rejects an empty sequence too. '
                'A relation where the requirer has asked for nothing is a bare '
                'ops.testing.Relation, or integrate(..., end="integrated").'
            )
        _check_protocols(self._protocols, 'protocols')

    @property
    def protocols(self) -> tuple[tracing.ReceiverProtocol, ...]:
        """The protocols this requirer asks to send traces with."""
        return self._protocols

    def _repr_args(self) -> list[str]:
        args = super()._repr_args()
        if self._protocols != _DEFAULT_PROTOCOLS:
            args.append(f'protocols={self._protocols!r}')
        return args

    def publish(self, state: testing.State) -> testing.State:
        """Write the simulated requirer's request.

        Recomputes the remote's application databag from ``protocols``, so the postcondition
        is "the requirer's data is correct for this state". It follows that calling it twice
        with nothing else changed leaves the state unchanged, and that a protocol this
        remote no longer asks for is gone from the databag rather than left behind.

        Only the remote's side is written, so the receivers the charm under test has
        published are left alone -- letting a test swap in a remote asking for something
        different and watch the charm reconcile.

        Unlike :meth:`RemoteProvider.publish`, this always writes: the requirer speaks first
        on this interface, so there is nothing to derive and nothing to wait for. ``tracing``
        requirers write to the application databag only, so the remote's unit databag is left
        as Juju leaves it.

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
        data = tracing.TracingRequirerAppData(receivers=list(self._protocols))
        return _replace_relation(state, relation, remote_app_data=_dump(data))


def _check_protocols(protocols: tuple[str, ...], argument: str) -> None:
    """Raise early where an argument names something that isn't a protocol of this interface."""
    known = sorted(_PORTS)
    unknown = [protocol for protocol in protocols if protocol not in _PORTS]
    if unknown:
        raise ValueError(
            f'{argument}={list(protocols)!r} names {unknown!r}, which the tracing interface '
            f'does not define. The protocols are {known!r}.'
        )


def _requested_protocols(databag: Mapping[str, str]) -> list[tracing.ReceiverProtocol] | None:
    """The protocols the charm has requested, or ``None`` if it hasn't requested any.

    ``None`` covers every way the request can be absent -- no key, invalid JSON, a payload
    the model rejects -- because that is exactly the set of cases a real provider treats as
    "this requirer isn't ready to talk tracing" and declines to answer.
    """
    try:
        # The library annotates the databag it loads from as a bare MutableMapping, so
        # pyright can't see the key and value types; the model it returns is typed.
        data = tracing.TracingRequirerAppData.load(dict(databag))  # pyright: ignore[reportUnknownMemberType]
    except (json.JSONDecodeError, pydantic.ValidationError, tracing.DataValidationError):
        return None
    return list(data.receivers)


def _dump(data: tracing.TracingProviderAppData | tracing.TracingRequirerAppData) -> dict[str, str]:
    """Render a databag model to the wire, through the library's own serialisation."""
    databag: dict[str, str] = {}
    # As above: dump writes into the mapping it is given, which is typed here even though
    # the library's own signature isn't.
    data.dump(databag)  # pyright: ignore[reportUnknownMemberType]
    return databag


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
