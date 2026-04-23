# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: Pebble log forwarding for OTLP endpoints."""

from cosl.juju_topology import JujuTopology

from charmlibs.interfaces.otlp._log_forwarder import PebbleLogForwarder
from charmlibs.interfaces.otlp._otlp import OtlpEndpoint

TOPOLOGY = JujuTopology(
    model='test-model',
    model_uuid='f4d59020-c8e7-4053-8044-a2c1e5591c7f',
    application='test-app',
    unit='test-app/0',
    charm_name='test-charm',
)


def test_build_otlp_layer_single_endpoint():
    # GIVEN a single OTLP endpoint that supports logs
    endpoints = {
        1: OtlpEndpoint(
            protocol='http',
            endpoint='http://collector:4318',
            telemetries=['logs', 'traces'],
        ),
    }

    # WHEN building the log forwarding layer
    layer = PebbleLogForwarder.build_otlp_layer(endpoints)

    # THEN the layer contains a single log target with type 'opentelemetry'
    targets = layer.to_dict()['log-targets']
    assert len(targets) == 1
    target = targets['otlp-1']
    assert target['type'] == 'opentelemetry'
    assert target['location'] == 'http://collector:4318'
    assert target['services'] == ['all']
    assert target['override'] == 'replace'
    # AND no labels are set when topology is not provided
    assert 'labels' not in target


def test_build_otlp_layer_with_topology():
    # GIVEN an OTLP endpoint that supports logs
    endpoints = {
        42: OtlpEndpoint(
            protocol='http',
            endpoint='http://collector:4318',
            telemetries=['logs'],
        ),
    }

    # WHEN building the log forwarding layer with topology
    layer = PebbleLogForwarder.build_otlp_layer(endpoints, topology=TOPOLOGY)

    # THEN the layer contains topology labels
    target = layer.to_dict()['log-targets']['otlp-42']
    assert target['labels'] == {
        'product': 'Juju',
        'charm': 'test-charm',
        'juju_model': 'test-model',
        'juju_model_uuid': 'f4d59020-c8e7-4053-8044-a2c1e5591c7f',
        'juju_application': 'test-app',
        'juju_unit': 'test-app/0',
    }


def test_build_otlp_layer_filters_non_logs_endpoints():
    # GIVEN endpoints with and without logs telemetry
    endpoints = {
        1: OtlpEndpoint(
            protocol='http',
            endpoint='http://collector-a:4318',
            telemetries=['logs', 'metrics'],
        ),
        2: OtlpEndpoint(
            protocol='grpc',
            endpoint='http://collector-b:4317',
            telemetries=['metrics', 'traces'],
        ),
        3: OtlpEndpoint(
            protocol='http',
            endpoint='http://collector-c:4318',
            telemetries=['traces'],
        ),
    }

    # WHEN building the log forwarding layer
    layer = PebbleLogForwarder.build_otlp_layer(endpoints)

    # THEN only the endpoint supporting 'logs' is included
    targets = layer.to_dict()['log-targets']
    assert len(targets) == 1
    assert 'otlp-1' in targets
    assert 'otlp-2' not in targets
    assert 'otlp-3' not in targets


def test_build_otlp_layer_empty_endpoints():
    # GIVEN no OTLP endpoints
    endpoints: dict[int, OtlpEndpoint] = {}

    # WHEN building the log forwarding layer
    layer = PebbleLogForwarder.build_otlp_layer(endpoints)

    # THEN the layer has an empty log-targets section
    assert layer.to_dict().get('log-targets', {}) == {}


def test_build_otlp_layer_multiple_log_endpoints():
    # GIVEN multiple OTLP endpoints that all support logs
    endpoints = {
        10: OtlpEndpoint(
            protocol='http',
            endpoint='http://loki-a:4318',
            telemetries=['logs'],
        ),
        20: OtlpEndpoint(
            protocol='grpc',
            endpoint='http://loki-b:4317',
            telemetries=['logs', 'metrics'],
        ),
    }

    # WHEN building the log forwarding layer
    layer = PebbleLogForwarder.build_otlp_layer(endpoints)

    # THEN both endpoints are included as separate log targets
    targets = layer.to_dict()['log-targets']
    assert len(targets) == 2
    assert targets['otlp-10']['location'] == 'http://loki-a:4318'
    assert targets['otlp-20']['location'] == 'http://loki-b:4317'


def test_build_otlp_layer_all_endpoints_lack_logs():
    # GIVEN endpoints that only support non-logs telemetries
    endpoints = {
        1: OtlpEndpoint(
            protocol='http',
            endpoint='http://collector:4318',
            telemetries=['metrics'],
        ),
        2: OtlpEndpoint(
            protocol='grpc',
            endpoint='http://collector:4317',
            telemetries=['traces'],
        ),
    }

    # WHEN building the log forwarding layer
    layer = PebbleLogForwarder.build_otlp_layer(endpoints)

    # THEN no log targets are created
    assert layer.to_dict().get('log-targets', {}) == {}


def test_build_log_target_enable():
    # GIVEN an OTLP endpoint
    endpoint = OtlpEndpoint(
        protocol='http',
        endpoint='http://collector:4318',
        telemetries=['logs'],
    )

    # WHEN building an enabled log target
    target = PebbleLogForwarder._build_log_target(endpoint)

    # THEN services is ['all'] and type is opentelemetry
    assert target['services'] == ['all']
    assert target['type'] == 'opentelemetry'
    assert target['location'] == 'http://collector:4318'


def test_build_log_target_disable():
    # GIVEN an OTLP endpoint
    endpoint = OtlpEndpoint(
        protocol='http',
        endpoint='http://collector:4318',
        telemetries=['logs'],
    )

    # WHEN building a disabled log target
    target = PebbleLogForwarder._build_log_target(endpoint, enable=False)

    # THEN services is ['-all'] to disable forwarding
    assert target['services'] == ['-all']
    assert target['type'] == 'opentelemetry'
    # AND no labels are set when disabled
    assert 'labels' not in target


def test_build_log_target_disable_ignores_topology():
    # GIVEN an OTLP endpoint and topology
    endpoint = OtlpEndpoint(
        protocol='http',
        endpoint='http://collector:4318',
        telemetries=['logs'],
    )

    # WHEN building a disabled log target with topology
    target = PebbleLogForwarder._build_log_target(endpoint, topology=TOPOLOGY, enable=False)

    # THEN labels are NOT included (labels are only for enabled targets)
    assert 'labels' not in target


def test_pebble_log_forwarder_importable_from_package():
    # GIVEN the public package API
    from charmlibs.interfaces.otlp import PebbleLogForwarder as Imported  # noqa: F811

    # THEN PebbleLogForwarder is importable
    assert Imported is PebbleLogForwarder
