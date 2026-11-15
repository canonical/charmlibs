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

"""Unit tests for the tracing provider."""

from typing import TypeAlias

import ops.testing
import pytest
from ops import CharmBase, Framework

from charmlibs.interfaces.tracing import (
    ReceiverProtocol,
    TracingEndpointProvider,
    TracingProviderAppData,
)

RECV_GRPC = (
    '[{"protocol": {"name": "otlp_grpc", "type": "grpc"} , "url": "foo.com:10"}, '
    '{"protocol": {"name": "otlp_http", "type": "http"}, "url": "http://foo.com:11"}] '
)
RECV_HTTP = (
    '[{"protocol": {"name": "otlp_grpc", "type": "grpc"} , "url": "foo.com:10"}, '
    '{"protocol": {"name": "otlp_http", "type": "http"}, "url": "http://foo.com:11"}] '
)


class MyCharm(CharmBase):
    external_url: str = "app.hostname"

    def __init__(self, framework: Framework):
        super().__init__(framework)
        self.tracing = TracingEndpointProvider(self, external_url=self.external_url)

        requested_receivers = set(self.tracing.requested_protocols())  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        if self.unit.is_leader():
            self.tracing.publish_receivers(
                [(p, self.get_receiver_url(p)) for p in requested_receivers]  # type: ignore[reportUnknownVariableType]
            )

    def get_receiver_url(self, protocol: ReceiverProtocol) -> str:
        if protocol == "otlp_grpc":
            return f"{self.external_url}:4317"
        elif protocol == "otlp_http":
            return f"http://{self.external_url}:4318"
        else:
            raise ValueError("unsupported")


Context: TypeAlias = ops.testing.Context[MyCharm]


@pytest.fixture
def context() -> Context:
    return ops.testing.Context(
        charm_type=MyCharm,
        meta={
            "name": "jolly",
            "provides": {"tracing": {"interface": "tracing", "limit": 1}},
        },
    )


@pytest.mark.parametrize("leader", (True, False))
def test_receiver_api(context: Context, leader: bool) -> None:
    # GIVEN two incoming tracing relations asking for otlp grpc and http respectively
    tracing_grpc = ops.testing.Relation(
        "tracing",
        remote_app_data={"receivers": '["otlp_grpc"]'},
        local_app_data={"receivers": RECV_GRPC},
    )
    tracing_http = ops.testing.Relation(
        "tracing",
        remote_app_data={"receivers": '["otlp_http"]'},
        local_app_data={"receivers": RECV_HTTP},
    )

    state = ops.testing.State(
        leader=leader,
        relations=[tracing_grpc, tracing_http],
    )

    # WHEN any event occurs
    with context(context.on.update_status(), state) as mgr:
        assert mgr.charm.tracing.requested_protocols() == {"otlp_grpc", "otlp_http"}
        state_out = mgr.run()

    # THEN both protocols are in the receivers published in the databag (local side)
    r_out = next(r for r in state_out.relations if r.id == tracing_http.id)
    assert sorted([
        r.protocol.name
        for r in TracingProviderAppData.load(r_out.local_app_data).receivers  # type: ignore[reportUnknownMemberType,reportArgumentType]
    ]) == ["otlp_grpc", "otlp_http"]


def test_leader_removes_receivers_on_relation_broken(context: Context) -> None:
    # GIVEN two incoming tracing relations asking for otel grpc and http respectively
    tracing_grpc = ops.testing.Relation(
        "tracing",
        remote_app_data={"receivers": '["otlp_grpc"]'},
        local_app_data={"receivers": RECV_GRPC},
    )
    tracing_http = ops.testing.Relation(
        "tracing",
        remote_app_data={"receivers": '["otlp_http"]'},
        local_app_data={"receivers": RECV_HTTP},
    )

    state = ops.testing.State(
        leader=True,
        relations=[tracing_grpc, tracing_http],
    )

    # WHEN the charm receives a relation-broken event for the one asking for otlp_grpc
    with context(context.on.relation_broken(tracing_grpc), state) as mgr:
        assert mgr.charm.tracing.requested_protocols() == {"otlp_http"}
        state_out = mgr.run()

    # THEN otlp_grpc is gone from the databag
    r_out = next(r for r in state_out.relations if r.id == tracing_http.id)
    assert sorted([
        r.protocol.name
        for r in TracingProviderAppData.load(r_out.local_app_data).receivers  # type: ignore[reportUnknownMemberType,reportArgumentType]
    ]) == ["otlp_http"]


def test_publish_receivers(context: Context) -> None:
    # GIVEN two incoming tracing relations asking for otlp grpc and http respectively
    tracing_grpc = ops.testing.Relation(
        "tracing",
        remote_app_data={"receivers": '["otlp_grpc"]'},
    )
    tracing_http = ops.testing.Relation(
        "tracing",
        remote_app_data={"receivers": '["otlp_http"]'},
    )

    # AND a leader unit
    state = ops.testing.State(
        leader=True,
        relations=[tracing_grpc, tracing_http],
    )

    # WHEN a relation_changed event occurs
    state_out = context.run(context.on.relation_changed(tracing_http), state)

    # THEN, two receiver endpoints should be published
    relation_out = state_out.get_relation(tracing_http.id)
    assert sorted([
        r.url
        for r in TracingProviderAppData.load(relation_out.local_app_data).receivers  # type: ignore[reportUnknownMemberType,reportArgumentType]
    ]) == ["app.hostname:4317", "http://app.hostname:4318"]


@pytest.mark.parametrize("hook", ("relation_changed", "relation_created", "relation_joined"))
def test_blank(context: Context, hook: str) -> None:
    tracing = ops.testing.Relation("tracing", remote_app_data={"receivers": "[]"})
    state = ops.testing.State(leader=True, relations={tracing})

    with context(getattr(context.on, hook)(tracing), state) as mgr:
        assert not mgr.charm.tracing.requested_protocols()
        out = mgr.run()

    assert out.get_relation(tracing).local_app_data == {"receivers": "[]"}
