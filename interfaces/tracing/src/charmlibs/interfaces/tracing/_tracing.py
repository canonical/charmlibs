# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
import enum
import json
import logging
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

import pydantic
from ops.charm import (
    CharmBase,
    CharmEvents,
    RelationBrokenEvent,
    RelationEvent,
    RelationRole,
)
from ops.framework import EventSource, Object
from ops.model import ModelError, Relation
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_DatabagModelT = TypeVar("_DatabagModelT", bound="DatabagModel")

DEFAULT_RELATION_NAME = "tracing"
RELATION_INTERFACE_NAME = "tracing"

# Supported list rationale https://github.com/canonical/tempo-coordinator-k8s-operator/issues/8
ReceiverProtocol = Literal[
    "zipkin",
    "otlp_grpc",
    "otlp_http",
    "jaeger_grpc",
    "jaeger_thrift_http",
]

RawReceiver = tuple[ReceiverProtocol, str]
# Helper type. A raw receiver is defined as a tuple consisting of the protocol name, and the
# (secured, if available) resolvable server url.


BUILTIN_JUJU_KEYS = {"ingress-address", "private-address", "egress-subnets"}


class TransportProtocolType(str, enum.Enum):
    """Receiver Type."""

    http = "http"
    grpc = "grpc"


receiver_protocol_to_transport_protocol: dict[ReceiverProtocol, TransportProtocolType] = {
    "zipkin": TransportProtocolType.http,
    "otlp_grpc": TransportProtocolType.grpc,
    "otlp_http": TransportProtocolType.http,
    "jaeger_thrift_http": TransportProtocolType.http,
    "jaeger_grpc": TransportProtocolType.grpc,
}
# A mapping between telemetry protocols and their corresponding transport protocol.


class TracingError(Exception):
    """Base class for custom errors raised by this library."""


class NotReadyError(TracingError):
    """Raised by the provider wrapper if a requirer hasn't published the required data (yet)."""


class ProtocolNotRequestedError(TracingError):
    """Raised if the user attempts to obtain an endpoint for a protocol it did not request."""


class DataValidationError(TracingError):
    """Raised when data validation fails on IPU relation data."""


class DataAccessPermissionError(TracingError):
    """Raised when follower units attempt leader-only operations."""


class AmbiguousRelationUsageError(TracingError):
    """Raised when one wrongly assumes that there can only be one relation on an endpoint."""


class DatabagModel(BaseModel):
    """Base databag model."""

    model_config = ConfigDict(
        # ignore any extra fields in the databag
        extra="ignore",
        # Allow instantiating this class by field name (instead of forcing alias).
        populate_by_name=True,
        # Custom config key: whether to nest the whole datastructure (as json)
        # under a field or spread it out at the toplevel.
        _NEST_UNDER=None,  # type: ignore
    )
    """Pydantic config."""

    @classmethod
    def load(cls: type[_DatabagModelT], databag: MutableMapping[str, str]) -> _DatabagModelT:
        """Load this model from a Juju databag."""
        nest_under = cls.model_config.get("_NEST_UNDER")
        if nest_under:
            return cls.model_validate(json.loads(databag[nest_under]))

        try:
            data = {
                k: json.loads(v)
                for k, v in databag.items()
                # Don't attempt to parse model-external values
                if k in {(f.alias or n) for n, f in cls.model_fields.items()}
            }
        except json.JSONDecodeError as e:
            msg = f"invalid databag contents: expecting json. {databag}"
            logger.error(msg)
            raise DataValidationError(msg) from e

        try:
            return cls.model_validate_json(json.dumps(data))
        except pydantic.ValidationError as e:
            msg = f"failed to validate databag: {databag}"
            logger.debug(msg, exc_info=True)
            raise DataValidationError(msg) from e

    def dump(
        self,
        databag: MutableMapping[str, str] | None = None,
        clear: bool = True,
    ) -> MutableMapping[str, str]:
        """Write the contents of this model to Juju databag.

        :param databag: the databag to write the data to.
        :param clear: ensure the databag is cleared before writing it.
        """
        if clear and databag:
            databag.clear()

        if databag is None:
            databag = {}
        nest_under = self.model_config.get("_NEST_UNDER")
        if nest_under:
            databag[nest_under] = self.model_dump_json(
                by_alias=True,
                # skip keys whose values are default
                exclude_defaults=True,
            )
            return databag

        dct = self.model_dump()
        for key, field in self.model_fields.items():  # type: ignore
            value = dct[key]
            if value == field.default:
                continue
            databag[field.alias or key] = json.dumps(value)

        return databag


# todo use models from charm-relation-interfaces
class ProtocolType(BaseModel):
    """Protocol Type."""

    model_config = ConfigDict(
        # Allow serializing enum values.
        use_enum_values=True
    )
    """Pydantic config."""

    name: str = Field(
        ...,
        description="Receiver protocol name. What protocols are supported "
        "(and what they are called) may differ per provider.",
        examples=["otlp_grpc", "otlp_http", "tempo_http"],
    )

    type: TransportProtocolType = Field(
        ...,
        description="The transport protocol used by this receiver.",
        examples=["http", "grpc"],
    )


class Receiver(BaseModel):
    """Specification of an active receiver."""

    protocol: ProtocolType = Field(..., description="Receiver protocol name and type.")
    url: str = Field(
        ...,
        description="URL at which the receiver is reachable. If there's an ingress, it would be "
        "the external URL. Otherwise, it would be the service's fqdn or internal IP. "
        "If the protocol type is grpc, the url will not contain a scheme.",
        examples=[
            "http://traefik_address:2331",
            "https://traefik_address:2331",
            "http://tempo_public_ip:2331",
            "https://tempo_public_ip:2331",
            "tempo_public_ip:2331",
        ],
    )


class TracingProviderAppData(DatabagModel):
    """Application databag model for the tracing provider."""

    receivers: list[Receiver] = Field(
        ...,
        description="List of all receivers enabled on the tracing provider.",
    )


class TracingRequirerAppData(DatabagModel):
    """Application databag model for the tracing requirer."""

    receivers: list[ReceiverProtocol]
    """Requested receivers."""


class _AutoSnapshotEvent(RelationEvent):
    __args__: tuple[str, ...] = ()
    __optional_kwargs__: dict[str, Any] = {}  # noqa  # unused

    @classmethod
    def __attrs__(cls) -> tuple[str, ...]:
        return cls.__args__ + tuple(cls.__optional_kwargs__.keys())

    def __init__(self, handle: Any, relation: Relation, *args: Any, **kwargs: Any) -> None:
        super().__init__(handle, relation)

        if not len(self.__args__) == len(args):
            raise TypeError(f"expected {len(self.__args__)} args, got {len(args)}")

        for attr, obj in zip(self.__args__, args, strict=False):
            setattr(self, attr, obj)
        for attr, default in self.__optional_kwargs__.items():
            obj = kwargs.get(attr, default)
            setattr(self, attr, obj)

    def snapshot(self) -> dict[str, Any]:
        dct = super().snapshot()
        for attr in self.__attrs__():
            obj = getattr(self, attr)
            try:
                dct[attr] = obj
            except ValueError as e:
                raise ValueError(
                    f"cannot automagically serialize {obj}: "
                    "override this method and do it "
                    "manually."
                ) from e

        return dct

    def restore(self, snapshot: dict[str, Any]) -> None:
        super().restore(snapshot)
        for attr, obj in snapshot.items():
            setattr(self, attr, obj)


class RelationNotFoundError(Exception):
    """Raised if no relation with the given name is found."""

    def __init__(self, relation_name: str):
        self.relation_name = relation_name
        self.message = f"No relation named {relation_name!r} found"
        super().__init__(self.message)


class RelationInterfaceMismatchError(Exception):
    """Raised if the relation with the given name has an unexpected interface."""

    def __init__(
        self,
        relation_name: str,
        expected_relation_interface: str,
        actual_relation_interface: str,
    ):
        self.relation_name = relation_name
        self.expected_relation_interface = expected_relation_interface
        self.actual_relation_interface = actual_relation_interface
        self.message = (
            f"The {relation_name!r} relation has {actual_relation_interface!r} as "
            f"interface rather than the expected {expected_relation_interface!r}"
        )

        super().__init__(self.message)


class RelationRoleMismatchError(Exception):
    """Raised if the relation with the given name has a different role than expected."""

    def __init__(
        self,
        relation_name: str,
        expected_relation_role: RelationRole,
        actual_relation_role: RelationRole,
    ):
        self.relation_name = relation_name
        self.expected_relation_interface = expected_relation_role
        self.actual_relation_role = actual_relation_role
        self.message = (
            f"The {relation_name} relation has role {actual_relation_role!r} rather than the "
            f"expected {expected_relation_role!r}"
        )

        super().__init__(self.message)


def _validate_relation_by_interface_and_direction(
    charm: CharmBase,
    relation_name: str,
    expected_relation_interface: str,
    expected_relation_role: RelationRole,
) -> None:
    """Validate a relation.

    Verifies that the `relation_name` provided: (1) exists in metadata.yaml,
    (2) declares as interface the interface name passed as `relation_interface`
    and (3) has the right "direction", i.e., it is a relation that `charm`
    provides or requires.

    Args:
        charm: a `CharmBase` object to scan for the matching relation.
        relation_name: the name of the relation to be verified.
        expected_relation_interface: the interface name to be matched by the
            relation named `relation_name`.
        expected_relation_role: whether the `relation_name` must be either
            provided or required by `charm`.

    Raises:
        RelationNotFoundError: If there is no relation in the charm's metadata.yaml
            with the same name as provided via `relation_name` argument.
        RelationInterfaceMismatchError: The relation with the same name as provided
            via `relation_name` argument does not have the same relation interface
            as specified via the `expected_relation_interface` argument.
        RelationRoleMismatchError: If the relation with the same name as provided
            via `relation_name` argument does not have the same role as specified
            via the `expected_relation_role` argument.
    """
    if relation_name not in charm.meta.relations:
        raise RelationNotFoundError(relation_name)

    relation = charm.meta.relations[relation_name]

    # fixme: why do we need to cast here?
    actual_relation_interface = cast("str", relation.interface_name)

    if actual_relation_interface != expected_relation_interface:
        raise RelationInterfaceMismatchError(
            relation_name, expected_relation_interface, actual_relation_interface
        )

    if expected_relation_role is RelationRole.provides:
        if relation_name not in charm.meta.provides:
            raise RelationRoleMismatchError(
                relation_name, RelationRole.provides, RelationRole.requires
            )
    elif expected_relation_role is RelationRole.requires:
        if relation_name not in charm.meta.requires:
            raise RelationRoleMismatchError(
                relation_name, RelationRole.requires, RelationRole.provides
            )
    else:
        raise TypeError(f"Unexpected RelationDirection: {expected_relation_role}")


class RequestEvent(RelationEvent):
    """Event emitted when a remote requests a tracing endpoint."""

    @property
    def requested_receivers(self) -> list[ReceiverProtocol]:
        """List of receiver protocols that have been requested."""
        relation = self.relation
        app = relation.app
        if not app:
            raise NotReadyError("relation.app is None")

        return TracingRequirerAppData.load(relation.data[app]).receivers


class BrokenEvent(RelationBrokenEvent):
    """Event emitted when a relation on tracing is broken."""


class TracingEndpointProviderEvents(CharmEvents):
    """TracingEndpointProvider events."""

    request = EventSource(RequestEvent)
    broken = EventSource(BrokenEvent)


class TracingEndpointProvider(Object):
    """Class representing a trace receiver service."""

    on = TracingEndpointProviderEvents()  # type: ignore

    def __init__(
        self,
        charm: CharmBase,
        external_url: str | None = None,
        relation_name: str = DEFAULT_RELATION_NAME,
    ):
        """Initialize.

        Args:
            charm: a `CharmBase` instance that manages this instance of the Tempo service.
            external_url: external address of the node hosting the tempo server,
                if an ingress is present.
            relation_name: an optional string name of the relation between `charm`
                and the Tempo charmed service. The default is "tracing".

        Raises:
            RelationNotFoundError: If there is no relation in the charm's metadata.yaml
                with the same name as provided via `relation_name` argument.
            RelationInterfaceMismatchError: The relation with the same name as provided
                via `relation_name` argument does not have the `tracing` relation
                interface.
            RelationRoleMismatchError: If the relation with the same name as provided
                via `relation_name` argument does not have the `RelationRole.requires`
                role.
        """
        _validate_relation_by_interface_and_direction(
            charm, relation_name, RELATION_INTERFACE_NAME, RelationRole.provides
        )

        super().__init__(charm, relation_name + "tracing-provider")
        self._charm = charm
        self._external_url = external_url
        self._relation_name = relation_name
        self.framework.observe(
            self._charm.on[relation_name].relation_joined, self._on_relation_event
        )
        self.framework.observe(
            self._charm.on[relation_name].relation_created, self._on_relation_event
        )
        self.framework.observe(
            self._charm.on[relation_name].relation_changed, self._on_relation_event
        )
        self.framework.observe(
            self._charm.on[relation_name].relation_broken,
            self._on_relation_broken_event,
        )

    def _on_relation_broken_event(self, e: RelationBrokenEvent) -> None:
        """Handle relation broken events."""
        self.on.broken.emit(e.relation)

    def _on_relation_event(self, e: RelationEvent) -> None:
        """Handle relation created/joined/changed events."""
        if self.is_requirer_ready(e.relation):
            self.on.request.emit(e.relation)

    def is_requirer_ready(self, relation: Relation) -> bool:
        """Attempt to determine if requirer has already populated app data."""
        try:
            self._get_requested_protocols(relation)
        except NotReadyError:
            return False
        return True

    @staticmethod
    def _get_requested_protocols(relation: Relation) -> list[ReceiverProtocol]:
        app = relation.app
        if not app:
            raise NotReadyError("relation.app is None")

        try:
            databag = TracingRequirerAppData.load(relation.data[app])
        except (json.JSONDecodeError, pydantic.ValidationError, DataValidationError):
            logger.info("relation %s is not ready to talk tracing", relation)
            raise NotReadyError() from None
        return databag.receivers

    def requested_protocols(self) -> set[ReceiverProtocol]:
        """All receiver protocols that have been requested by our related apps."""
        requested_protocols: set[ReceiverProtocol] = set()
        for relation in self.relations:
            try:
                protocols = self._get_requested_protocols(relation)
            except NotReadyError:
                continue
            requested_protocols.update(protocols)
        return requested_protocols

    @property
    def relations(self) -> list[Relation]:
        """All relations active on this endpoint."""
        return self._charm.model.relations[self._relation_name]

    def publish_receivers(self, receivers: Sequence[RawReceiver]) -> None:
        """Let all requirers know that these receivers are active and listening."""
        if not self._charm.unit.is_leader():
            raise RuntimeError("only leader can do this")

        for relation in self.relations:
            try:
                TracingProviderAppData(
                    receivers=[
                        Receiver(
                            url=url,
                            protocol=ProtocolType(
                                name=protocol,
                                type=receiver_protocol_to_transport_protocol[protocol],
                            ),
                        )
                        for protocol, url in receivers
                    ],
                ).dump(relation.data[self._charm.app])

            except ModelError as e:  # noqa: PERF203
                # args are bytes
                msg = e.args[0]
                if isinstance(msg, bytes) and msg.startswith(
                    b"ERROR cannot read relation application settings: permission denied"
                ):
                    logger.error(
                        "encountered error %s while attempting to update_relation_data."
                        "The relation must be gone.",
                        e,
                    )
                    continue
                raise


class EndpointRemovedEvent(RelationBrokenEvent):
    """Event representing a change in one of the receiver endpoints."""


class EndpointChangedEvent(_AutoSnapshotEvent):
    """Event representing a change in one of the receiver endpoints."""

    __args__ = ("_receivers",)

    @property
    def receivers(self) -> list[Receiver]:
        """Cast receivers back from dict."""
        return [Receiver(**i) for i in self._receivers]  # type: ignore


class TracingEndpointRequirerEvents(CharmEvents):
    """TracingEndpointRequirer events."""

    endpoint_changed = EventSource(EndpointChangedEvent)
    endpoint_removed = EventSource(EndpointRemovedEvent)


class TracingEndpointRequirer(Object):
    """A tracing endpoint for Tempo."""

    on = TracingEndpointRequirerEvents()  # type: ignore

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
        protocols: list[ReceiverProtocol] | None = None,
    ):
        """Construct a tracing requirer for a Tempo charm.

        If your application supports pushing traces to a distributed tracing backend, the
        `TracingEndpointRequirer` object enables your charm to easily access endpoint information
        exchanged over a `tracing` relation interface.

        Args:
            charm: a `CharmBase` object that manages this
                `TracingEndpointRequirer` object. Typically, this is `self` in the instantiating
                class.
            relation_name: an optional string name of the relation between `charm`
                and the Tempo charmed service. The default is "tracing". It is strongly
                advised not to change the default, so that people deploying your charm will have a
                consistent experience with all other charms that provide tracing endpoints.
            protocols: optional list of protocols that the charm intends to send traces with.
                The provider will enable receivers for these and only these protocols,
                so be sure to enable all protocols the charm or its workload are going to need.

        Raises:
            RelationNotFoundError: If there is no relation in the charm's metadata.yaml
                with the same name as provided via `relation_name` argument.
            RelationInterfaceMismatchError: The relation with the same name as provided
                via `relation_name` argument does not have the `tracing` relation
                interface.
            RelationRoleMismatchError: If the relation with the same name as provided
                via `relation_name` argument does not have the `RelationRole.provides`
                role.
        """
        _validate_relation_by_interface_and_direction(
            charm, relation_name, RELATION_INTERFACE_NAME, RelationRole.requires
        )

        super().__init__(charm, relation_name)

        self._is_single_endpoint = charm.meta.relations[relation_name].limit == 1

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[self._relation_name]
        self.framework.observe(events.relation_changed, self._on_tracing_relation_changed)
        self.framework.observe(events.relation_broken, self._on_tracing_relation_broken)

        if protocols and self._charm.unit.is_leader():
            # we can't be sure that the current event context supports read/writing relation data
            # for this relation, so we catch ModelErrors. This is because we're doing this
            # in init.
            try:
                self.request_protocols(protocols)
            except ModelError as e:
                logger.error(
                    "encountered error %s while attempting to request_protocols."
                    "The relation must be gone.",
                    e,
                )
                pass

    def request_protocols(
        self, protocols: Sequence[ReceiverProtocol], relation: Relation | None = None
    ) -> None:
        """Publish the list of protocols which the provider should activate."""
        # todo: should we check if _is_single_endpoint and len(self.relations) > 1 and raise, here?
        relations = [relation] if relation else self.relations

        if not protocols:
            # empty sequence
            raise ValueError(
                "You need to pass a nonempty sequence of protocols to `request_protocols`."
            )

        if self._charm.unit.is_leader():
            for relation in relations:
                TracingRequirerAppData(
                    receivers=list(protocols),
                ).dump(relation.data[self._charm.app])
        else:
            raise DataAccessPermissionError("only leaders can request_protocols")

    @property
    def relations(self) -> list[Relation]:
        """The tracing relations associated with this endpoint."""
        return self._charm.model.relations[self._relation_name]

    @property
    def _relation(self) -> Relation | None:
        """If this wraps a single endpoint, the relation bound to it, if any."""
        if not self._is_single_endpoint:
            objname = type(self).__name__
            raise AmbiguousRelationUsageError(
                f"This {objname} wraps a {self._relation_name} endpoint that has "
                "limit != 1. We can't determine what relation, of the possibly many, you are "
                f"talking about. Please pass a relation instance while calling {objname}, "
                "or set limit=1 in the charm metadata."
            )
        relations = self.relations
        return relations[0] if relations else None

    def is_ready(self, relation: Relation | None = None) -> bool:
        """Is this endpoint ready?"""
        relation = relation or self._relation
        if not relation:
            logger.debug("no relation on %r: tracing not ready", self._relation_name)
            return False
        if not relation.app:
            logger.error("%s event received but there is no relation.app", relation)
            return False
        try:
            databag = dict(relation.data[relation.app])
            TracingProviderAppData.load(databag)

        except (json.JSONDecodeError, pydantic.ValidationError, DataValidationError):
            logger.info("failed validating relation data for %s", relation)
            return False
        return True

    def _on_tracing_relation_changed(self, event: RelationEvent) -> None:
        """Notify the providers that there is new endpoint information available."""
        relation = event.relation
        if not self.is_ready(relation):
            self.on.endpoint_removed.emit(relation)
            return

        data = TracingProviderAppData.load(relation.data[relation.app])
        self.on.endpoint_changed.emit(relation, [i.dict() for i in data.receivers])  # type: ignore

    def _on_tracing_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Notify the providers that the endpoint is broken."""
        relation = event.relation
        self.on.endpoint_removed.emit(relation)

    def get_all_endpoints(self, relation: Relation | None = None) -> TracingProviderAppData | None:
        """Unmarshalled relation data."""
        relation = relation or self._relation
        if not self.is_ready(relation):
            return
        return TracingProviderAppData.load(relation.data[relation.app])  # type: ignore

    def _get_endpoint(self, relation: Relation | None, protocol: ReceiverProtocol) -> str | None:
        app_data = self.get_all_endpoints(relation)
        if not app_data:
            return None
        receivers: list[Receiver] = list(
            filter(lambda i: i.protocol.name == protocol, app_data.receivers)
        )
        if not receivers:
            # it can happen if the charm requests tracing protocols, but the relay
            # (such as grafana-agent) isn't yet connected to the tracing backend. In this case,
            # it's not an error the charm author can do anything about
            logger.warning("no receiver found with protocol=%r.", protocol)
            return
        if len(receivers) > 1:
            # if we have more than 1 receiver that matches,
            # it shouldn't matter which receiver we'll be using.
            logger.warning(
                "too many receivers with protocol=%r; using first one. Found: %s",
                protocol,
                receivers,
            )

        receiver = receivers[0]
        return receiver.url

    def get_endpoint(
        self, protocol: ReceiverProtocol, relation: Relation | None = None
    ) -> str | None:
        """Receiver endpoint for the given protocol.

        It could happen that this function gets called before the provider publishes the endpoints.
        In such a scenario, if a non-leader unit calls this function, a permission denied exception
        will be raised due to restricted access. To prevent this, this function needs to be guarded
        by the `is_ready` check.

        Raises:
            ProtocolNotRequestedError: If the charm unit is the leader unit and attempts to obtain
                an endpoint for a protocol it did not request.
        """
        endpoint = self._get_endpoint(relation or self._relation, protocol=protocol)
        if not endpoint:
            requested_protocols: set[ReceiverProtocol] = set()
            relations = [relation] if relation else self.relations
            for relation in relations:
                try:
                    databag = TracingRequirerAppData.load(relation.data[self._charm.app])
                except DataValidationError:
                    continue

                requested_protocols.update(databag.receivers)

            if protocol not in requested_protocols:
                raise ProtocolNotRequestedError(protocol, relation)

            return None
        return endpoint


# Note: this function should be deprecated
# it's helpful when tracing.py and charm_tracing.py are used together
# the path forward should be charmlibs.xx.tracing and ops[tracing].
def charm_tracing_config(
    endpoint_requirer: TracingEndpointRequirer, cert_path: Path | str | None
) -> tuple[str | None, str | None]:
    """Return the charm_tracing config you likely want.

    If no endpoint is provided:
     disable charm tracing.
    If https endpoint is provided but cert_path is not found on disk:
     disable charm tracing.
    If https endpoint is provided and cert_path is None:
     ERROR
    Else:
     proceed with charm tracing (with or without tls, as appropriate)

    Usage:
    >>> from lib.charms.tempo_coordinator_k8s.v0.charm_tracing import trace_charm
    >>> from charmlibs.interfaces.tracing import charm_tracing_config
    >>> @trace_charm(tracing_endpoint="my_endpoint", cert_path="cert_path")
    >>> class MyCharm(...):
    >>>     _cert_path = "/path/to/cert/on/charm/container.crt"
    >>>     def __init__(self, ...):
    >>>         self.tracing = TracingEndpointRequirer(...)
    >>>         self.my_endpoint, self.cert_path = charm_tracing_config(
    ...             self.tracing, self._cert_path)
    """
    if not endpoint_requirer.is_ready():
        return None, None

    try:
        endpoint = endpoint_requirer.get_endpoint("otlp_http")
    except ModelError as e:
        if e.args[0] == "ERROR permission denied\n":
            # this can happen the app databag doesn't have data,
            # or we're breaking the relation.
            return None, None
        raise

    if not endpoint:
        return None, None

    is_https = endpoint.startswith("https://")

    if is_https:
        if cert_path is None or not Path(cert_path).exists():
            # disable charm tracing until we obtain a cert to prevent tls errors
            logger.error(
                "Tracing endpoint is https, but no server_cert has been passed."
                "Please point @trace_charm to a `server_cert` attr. "
                "This might also mean that the tracing provider is related to a "
                "certificates provider, but this application is not (yet). "
                "In that case, you might just have to wait a bit for the certificates "
                "integration to settle. "
            )
            return None, None
        return endpoint, str(cert_path)
    else:
        return endpoint, None
