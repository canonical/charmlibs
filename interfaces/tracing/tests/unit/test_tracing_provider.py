# Copyright 2026 Canonical Ltd.
import json
from typing import TypeAlias

import ops.testing
import pytest

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


class MyCharm(ops.CharmBase):
    external_url: str = "default-host.example"

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.tracing = TracingEndpointProvider(self, external_url=self.external_url)

    def todo(self):
        requested_protocols = set(self.tracing.requested_protocols())
        requested_receivers = requested_protocols
        if self.unit.is_leader():
            self.tracing.publish_receivers(
                [(p, self.get_receiver_url(p)) for p in requested_receivers]
            )

    def get_receiver_url(self, protocol: ReceiverProtocol) -> str:
        if protocol == "otlp_grpc":
            return f"{self.external_url}:10"
        elif protocol == "otlp_http":
            return f"http://{self.external_url}:11"
        else:
            raise ValueError("unsupported")


Context: TypeAlias = ops.testing.Context[MyCharm]


@pytest.mark.parametrize("leader", (True, False))
def test_receiver_api(context: Context, leader: bool):
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
        charm = mgr.charm
        assert charm._requested_receivers == ("otlp_grpc", "otlp_http")
        state_out = mgr.run()

    # THEN both protocols are in the receivers published in the databag (local side)

    r_out = next(r for r in state_out.relations if r.id == tracing_http.id)
    assert sorted([
        r.protocol.name for r in TracingProviderAppData.load(r_out.local_app_data).receivers
    ]) == ["otlp_grpc", "otlp_http"]


def test_leader_removes_receivers_on_relation_broken(context: Context):
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
        charm = mgr.charm
        assert charm._requested_receivers == ("otlp_http",)
        state_out = mgr.run()

    # THEN otlp_grpc is gone from the databag
    r_out = next(r for r in state_out.relations if r.id == tracing_http.id)
    assert sorted([
        r.protocol.name for r in TracingProviderAppData.load(r_out.local_app_data).receivers
    ]) == ["otlp_http"]


# FIXME: inject this into the charm
#@patch(
#    "charm.TempoCoordinatorCharm.app_hostname",
#    PropertyMock(return_value="app.hostname"),
#)
def test_publish_receivers(context: Context):
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

    # THEN, two receiver endpoints should be published using the mocked value of app_hostname
    relation_out = state_out.get_relation(tracing_http.id)
    assert sorted([
        r.url for r in TracingProviderAppData.load(relation_out.local_app_data).receivers
    ]) == ["app.hostname:4317", "http://app.hostname:4318"]


@pytest.mark.parametrize("hook", ("relation_changed", "relation_created", "relation_joined"))
def test_tracing_v2_endpoint_published(context: Context, hook: str):
    tracing = ops.testing.Relation("tracing", remote_app_data={"receivers": "[]"})
    state = ops.testing.State(leader=True, relations={tracing})

    with context(getattr(context.on, hook)(tracing), state) as mgr:
        assert len(mgr.charm._requested_receivers) == 1
        out = mgr.run()

    tracing_out = out.get_relations(tracing.endpoint)[0]
    expected_data = [
        {
            "protocol": {"name": "otlp_http", "type": "http"},
            "url": "http://default-host.example:4318",
        },
    ]

    assert (
        sorted(
            json.loads(tracing_out.local_app_data["receivers"]),
            key=lambda x: x["protocol"]["name"],
        )
        == expected_data
    )
