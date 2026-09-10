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

"""Unit tests for the tracing requirer."""

import socket
from contextlib import nullcontext

import pytest
from ops import CharmBase, Framework, RelationBrokenEvent, RelationChangedEvent
from ops.testing import Context, Relation, State

from charmlibs.interfaces.tracing import (
    DataAccessPermissionError,
    EndpointChangedEvent,
    EndpointRemovedEvent,
    ProtocolNotRequestedError,
    ReceiverProtocol,
    TracingEndpointRequirer,
    TracingRequirerAppData,
)


class MyCharm(CharmBase):
    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.tracing = TracingEndpointRequirer(self, protocols=["otlp_grpc"])
        framework.observe(self.tracing.on.endpoint_changed, self._on_endpoint_changed)

    def _on_endpoint_changed(self, e: EndpointChangedEvent) -> None:
        pass


@pytest.fixture
def context() -> Context[MyCharm]:
    return Context(
        charm_type=MyCharm,
        meta={
            "name": "jolly",
            "requires": {"tracing": {"interface": "tracing", "limit": 1}},
        },
    )


@pytest.mark.parametrize("leader", (True, False))
def test_requirer_api(context: Context[MyCharm], leader: bool) -> None:
    host = socket.getfqdn()
    tracing_rel = Relation(
        "tracing",
        remote_app_data={
            "receivers": f'[{{"protocol": {{"name": "otlp_grpc", "type": "grpc"}}, "url": "{host}:4317"}}, '
            f'{{"protocol": {{"name": "otlp_http", "type": "http"}}, "url": "http://{host}:4318"}}, '
            f'{{"protocol": {{"name": "zipkin", "type": "http"}}, "url": "http://{host}:9411" }}]',
        },
    )
    state = State(leader=leader, relations=[tracing_rel])

    with context(context.on.relation_changed(tracing_rel), state) as mgr:
        charm = mgr.charm
        assert charm.tracing.get_endpoint("otlp_grpc") == f"{host}:4317"
        assert charm.tracing.get_endpoint("otlp_http") == f"http://{host}:4318"
        assert charm.tracing.get_endpoint("zipkin") == f"http://{host}:9411"

        rel = charm.model.get_relation("tracing")
        assert charm.tracing.is_ready(rel)

    _rchanged, epchanged = context.emitted_events
    assert isinstance(epchanged, EndpointChangedEvent)
    assert epchanged.receivers[0].protocol.name == "otlp_grpc"
    assert epchanged.receivers[1].protocol.name == "otlp_http"
    assert epchanged.receivers[2].protocol.name == "zipkin"


@pytest.mark.parametrize("leader", (True, False))
def test_requirer_api_with_internal_scheme(context: Context[MyCharm], leader: bool) -> None:
    host = socket.getfqdn()
    tracing_rel = Relation(
        "tracing",
        remote_app_data={
            "receivers": f'[{{"protocol": {{"name": "otlp_grpc", "type": "grpc"}} , "url": "{host}:4317"}}, '
            f'{{"protocol": {{"name": "otlp_http", "type": "http"}}, "url": "https://{host}:4318"}}, '
            f'{{"protocol": {{"name": "zipkin", "type": "http"}}, "url":  "https://{host}:9411"}}]',
        },
    )
    state = State(leader=leader, relations=[tracing_rel])

    with context(context.on.relation_changed(tracing_rel), state) as mgr:
        charm = mgr.charm
        assert charm.tracing.get_endpoint("otlp_grpc") == f"{host}:4317"
        assert charm.tracing.get_endpoint("otlp_http") == f"https://{host}:4318"
        assert charm.tracing.get_endpoint("zipkin") == f"https://{host}:9411"

        rel = charm.model.get_relation("tracing")
        assert charm.tracing.is_ready(rel)

    _rchanged, epchanged = context.emitted_events
    assert isinstance(epchanged, EndpointChangedEvent)
    assert epchanged.receivers[0].protocol.name == "otlp_grpc"


@pytest.mark.parametrize("leader", (True, False))
def test_ingressed_requirer_api(context: Context[MyCharm], leader: bool) -> None:
    # WHEN external_url is present in remote app databag
    external_url = "http://1.2.3.4"
    tracing_rel = Relation(
        "tracing",
        remote_app_data={
            "receivers": f'[{{"protocol": {{"name": "otlp_grpc", "type": "grpc"}}, "url": "{external_url.split("://")[1]}:4317" }}, '
            f'{{"protocol": {{"name": "otlp_http", "type": "http"}} , "url": "{external_url}:4318" }}, '
            f'{{"protocol": {{"name": "zipkin", "type": "http"}} , "url": "{external_url}:9411" }}]',
        },
    )
    state = State(leader=leader, relations=[tracing_rel])

    # THEN get_endpoint uses external URL instead of the host
    receiver_ports: list[tuple[ReceiverProtocol, int]] = [
        ("otlp_grpc", 4317),
        ("otlp_http", 4318),
        ("zipkin", 9411),
    ]
    with context(context.on.relation_changed(tracing_rel), state) as mgr:
        charm = mgr.charm
        assert (
            charm.tracing.get_endpoint("otlp_grpc")
            == f"{external_url.split('://')[1]}:{receiver_ports[0][1]}"
        )
        for proto, port in receiver_ports[1:]:
            assert charm.tracing.get_endpoint(proto) == f"{external_url}:{port}"

        rel = charm.model.get_relation("tracing")
        assert charm.tracing.is_ready(rel)

    _rchanged, epchanged = context.emitted_events
    assert isinstance(epchanged, EndpointChangedEvent)
    assert epchanged.receivers[0].protocol.name == "otlp_grpc"


@pytest.mark.parametrize(
    "data",
    (
        {
            "ingesters": '[{"protocol": "otlp_grpc", "port": 9999}]',
            "bar": "baz",
        },
        {
            "host": "foo.com",
            "bar": "baz",
        },
        {
            "ingesters": '[{"burp": "barp", "port": 3200}]',
            "host": "foo.com",
        },
        {
            "ingesters": '[{"protocol": "tempo", "burp": "borp"}]',
            "host": "foo.com",
        },
    ),
)
@pytest.mark.parametrize("leader", (True, False))
def test_invalid_data(context: Context[MyCharm], data: dict[str, str], leader: bool) -> None:
    tracing_rel = Relation(
        "tracing",
        remote_app_data=data,
    )
    state = State(leader=leader, relations=[tracing_rel])

    with context(context.on.relation_changed(tracing_rel), state) as mgr:
        charm = mgr.charm
        mgr.run()
        rel = charm.model.get_relation("tracing")
        assert not charm.tracing.is_ready(rel)

    emitted_events = context.emitted_events
    assert len(emitted_events) == 2
    rchanged, rremoved = emitted_events
    assert isinstance(rchanged, RelationChangedEvent)
    assert isinstance(rremoved, EndpointRemovedEvent)


@pytest.mark.parametrize("leader", (True, False))
def test_broken(context: Context[MyCharm], leader: bool) -> None:
    tracing_rel = Relation("tracing")
    state = State(leader=leader, relations=[tracing_rel])

    context.run(context.on.relation_broken(tracing_rel), state)

    emitted_events = context.emitted_events
    assert len(emitted_events) == 2
    rchanged, ebroken = emitted_events
    assert isinstance(rchanged, RelationBrokenEvent)
    assert isinstance(ebroken, EndpointRemovedEvent)


@pytest.mark.parametrize("leader", (True, False))
def test_requested_not_yet_replied(context: Context[MyCharm], leader: bool) -> None:
    # GIVEN an empty tracing relation
    tracing_rel = Relation("tracing")
    state = State(leader=leader, relations=[tracing_rel])

    # WHEN we receive a created event
    with context(context.on.relation_created(tracing_rel), state) as mgr:
        charm = mgr.charm

        # THEN a leader can request a protocol, a follower cannot
        ctx = pytest.raises(DataAccessPermissionError) if not leader else nullcontext()
        with ctx:
            charm.tracing.request_protocols(["otlp_http"])

        # AND THEN a leader cannot find any endpoint yet, a follower gets an error
        ctx = pytest.raises(ProtocolNotRequestedError) if not leader else nullcontext()
        with ctx:
            assert not charm.tracing.get_endpoint("otlp_http")


def test_requirer_writes_requested_protocols_to_databag(context: Context[MyCharm]) -> None:
    # GIVEN an empty tracing relation and a leader unit
    tracing_rel = Relation("tracing")
    state = State(leader=True, relations=[tracing_rel])

    # WHEN a relation-created event fires (MyCharm requests otlp_grpc in __init__)
    state_out = context.run(context.on.relation_created(tracing_rel), state)

    # THEN the requirer has written the requested protocols to its app databag
    relation_out = state_out.get_relation(tracing_rel.id)
    assert relation_out.local_app_data == TracingRequirerAppData(receivers=["otlp_grpc"]).dump()  # type: ignore[operator]


@pytest.mark.parametrize("leader", (True, False))
def test_not_requested_raises(context: Context[MyCharm], leader: bool) -> None:
    tracing_rel = Relation("tracing")
    state = State(leader=leader, relations=[tracing_rel])

    with context(context.on.relation_created(tracing_rel), state) as mgr:
        charm = mgr.charm
        with pytest.raises(ProtocolNotRequestedError):
            charm.tracing.get_endpoint("otlp_http")
