# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: OTLP endpoint handling."""

import json
from collections.abc import Sequence
from typing import Any, Final, Literal

import ops
import pytest
from ops import testing
from ops.testing import Relation, State

from charmlibs.interfaces.otlp._otlp import DEFAULT_PROVIDER_RELATION_NAME as RECEIVE
from charmlibs.interfaces.otlp._otlp import DEFAULT_REQUIRER_RELATION_NAME as SEND
from charmlibs.interfaces.otlp._otlp import (
    OtlpProvider,
    OtlpRequirer,
    _OtlpEndpoint,
    _OtlpProviderAppData,
)
from conftest import ALL_PROTOCOLS, ALL_TELEMETRIES

PROTOCOLS: Final[list[Literal['http', 'grpc']]] = ['http', 'grpc']
TELEMETRIES: Final[list[Literal['metrics', 'logs']]] = ['metrics', 'logs']


def test_new_endpoint_key_is_ignored_by_databag_model():
    # GIVEN the provider offers a new endpoint type (protocol or telemetry)
    # * the requirer does not support this new endpoint type
    endpoint = {
        'protocol': 'new_protocol',
        'endpoint': 'http://host:4317',
        'telemetries': ['logs'],
        'insecure': False,
        'new_key': 'value',
    }

    # WHEN validating the provider databag model, which the requirer uses to access endpoints
    # THEN the validation succeeds
    provider_databag: _OtlpProviderAppData = _OtlpProviderAppData.model_validate({
        'endpoints': [endpoint]
    })
    assert provider_databag
    # AND the new endpoint key is ignored
    assert 'new_key' not in provider_databag.endpoints[0].model_dump()


@pytest.mark.parametrize(
    'provides, otlp_endpoint',
    (
        (
            # GIVEN an endpoint with an invalid protocol
            # * an endpoint with a valid protocol
            {
                'endpoints': json.dumps([
                    {
                        'protocol': 'new_protocol',
                        'endpoint': 'http://host:0000',
                        'telemetries': ['metrics'],
                        'insecure': False,
                    },
                    {
                        'protocol': 'http',
                        'endpoint': 'http://host:4317',
                        'telemetries': ['metrics'],
                        'insecure': False,
                    },
                ]),
            },
            _OtlpEndpoint(
                protocol='http',
                endpoint='http://host:4317',
                telemetries=['metrics'],
            ),
        ),
        (
            # GIVEN an endpoint with valid and invalid telemetries
            {
                'endpoints': json.dumps([
                    {
                        'protocol': 'http',
                        'endpoint': 'http://host:4317',
                        'telemetries': ['logs', 'new_telemetry', 'traces'],
                        'insecure': False,
                    },
                ]),
            },
            _OtlpEndpoint(
                protocol='http', endpoint='http://host:4317', telemetries=['logs', 'traces']
            ),
        ),
        (
            # GIVEN a valid endpoint
            # * an invalid databag key
            {
                'endpoints': json.dumps([
                    {
                        'protocol': 'http',
                        'endpoint': 'http://host:4317',
                        'telemetries': ['metrics'],
                        'insecure': False,
                    }
                ]),
                'does_not': '"exist"',
            },
            _OtlpEndpoint(
                protocol='http',
                endpoint='http://host:4317',
                telemetries=['metrics'],
            ),
        ),
    ),
)
def test_send_otlp_invalid_databag(
    otlp_requirer_ctx: testing.Context[ops.CharmBase],
    provides: dict[str, Any],
    otlp_endpoint: _OtlpEndpoint,
):
    # GIVEN a remote app provides an _OtlpEndpoint
    # WHEN they are related over the "send-otlp" endpoint
    provider = Relation(SEND, id=123, remote_app_data=provides)
    state = State(relations=[provider], leader=True)

    with otlp_requirer_ctx(otlp_requirer_ctx.on.update_status(), state=state) as mgr:
        # WHEN the requirer processes the relation data
        # * the requirer supports all protocols and telemetries
        # THEN the requirer does not raise an error
        # * the returned endpoint does not include new protocols or telemetries
        assert mgr.run()
        endpoints = OtlpRequirer(mgr.charm, SEND, ALL_PROTOCOLS, ALL_TELEMETRIES).endpoints
        assert endpoints[123].model_dump() == otlp_endpoint.model_dump()


@pytest.mark.parametrize(
    'protocols, telemetries, expected',
    [
        (
            ALL_PROTOCOLS,
            ALL_TELEMETRIES,
            {
                123: _OtlpEndpoint(
                    protocol='http',
                    endpoint='http://provider-123:4318',
                    telemetries=['logs', 'metrics'],
                ),
                456: _OtlpEndpoint(
                    protocol='grpc', endpoint='http://provider-456:4317', telemetries=['traces']
                ),
            },
        ),
        (
            ['grpc'],
            ALL_TELEMETRIES,
            {
                456: _OtlpEndpoint(
                    protocol='grpc', endpoint='http://provider-456:4317', telemetries=['traces']
                )
            },
        ),
        (
            ALL_PROTOCOLS,
            ['metrics'],
            {
                123: _OtlpEndpoint(
                    protocol='http', endpoint='http://provider-123:4318', telemetries=['metrics']
                ),
                456: _OtlpEndpoint(
                    protocol='http', endpoint='http://provider-456:4318', telemetries=['metrics']
                ),
            },
        ),
        (['http'], ['traces'], {}),
    ],
)
def test_send_otlp_with_varying_requirer_support(
    otlp_requirer_ctx: testing.Context[ops.CharmBase],
    protocols: Sequence[Literal['http', 'grpc']],
    telemetries: Sequence[Literal['logs', 'metrics', 'traces']],
    expected: dict[int, _OtlpEndpoint],
):
    # GIVEN a remote app provides multiple _OtlpEndpoints
    remote_app_data_1 = {
        'endpoints': json.dumps([
            {
                'protocol': 'http',
                'endpoint': 'http://provider-123:4318',
                'telemetries': ['logs', 'metrics'],
                'insecure': False,
            }
        ])
    }
    remote_app_data_2 = {
        'endpoints': json.dumps([
            {
                'protocol': 'grpc',
                'endpoint': 'http://provider-456:4317',
                'telemetries': ['traces'],
                'insecure': False,
            },
            {
                'protocol': 'http',
                'endpoint': 'http://provider-456:4318',
                'telemetries': ['metrics'],
                'insecure': False,
            },
        ])
    }

    # WHEN they are related over the "send-otlp" endpoint
    provider_0 = Relation(SEND, id=123, remote_app_data=remote_app_data_1)
    provider_1 = Relation(SEND, id=456, remote_app_data=remote_app_data_2)
    state = State(relations=[provider_0, provider_1], leader=True)

    # AND WHEN the requirer has varying support for OTLP protocols and telemetries
    with otlp_requirer_ctx(otlp_requirer_ctx.on.update_status(), state=state) as mgr:
        remote_endpoints = OtlpRequirer(mgr.charm, SEND, protocols, telemetries).endpoints

    # THEN the returned endpoints are filtered accordingly
    assert {k: v.model_dump() for k, v in remote_endpoints.items()} == {
        k: v.model_dump() for k, v in expected.items()
    }


def test_send_otlp(otlp_requirer_ctx: testing.Context[ops.CharmBase]):
    # GIVEN a remote app provides multiple _OtlpEndpoints
    remote_app_data_1 = {
        'endpoints': json.dumps([
            {
                'protocol': 'http',
                'endpoint': 'http://provider-123:4318',
                'telemetries': ['logs', 'metrics'],
                'insecure': False,
            }
        ])
    }
    remote_app_data_2 = {
        'endpoints': json.dumps([
            {
                'protocol': 'grpc',
                'endpoint': 'http://provider-456:4317',
                'telemetries': ['traces'],
                'insecure': False,
            },
            {
                'protocol': 'http',
                'endpoint': 'http://provider-456:4318',
                'telemetries': ['metrics'],
                'insecure': False,
            },
        ])
    }

    expected_endpoints = {
        456: _OtlpEndpoint(
            protocol='http', endpoint='http://provider-456:4318', telemetries=['metrics']
        ),
        123: _OtlpEndpoint(
            protocol='http', endpoint='http://provider-123:4318', telemetries=['logs', 'metrics']
        ),
    }

    # WHEN they are related over the "send-otlp" endpoint
    provider_1 = Relation(SEND, id=123, remote_app_data=remote_app_data_1)
    provider_2 = Relation(SEND, id=456, remote_app_data=remote_app_data_2)
    state = State(relations=[provider_1, provider_2], leader=True)

    # AND WHEN otelcol supports a subset of OTLP protocols and telemetries
    with otlp_requirer_ctx(otlp_requirer_ctx.on.update_status(), state=state) as mgr:
        remote_endpoints = OtlpRequirer(mgr.charm, SEND, PROTOCOLS, TELEMETRIES).endpoints

    # THEN the returned endpoints are filtered accordingly
    assert {k: v.model_dump() for k, v in remote_endpoints.items()} == {
        k: v.model_dump() for k, v in expected_endpoints.items()
    }


def test_receive_otlp(otlp_provider_ctx: testing.Context[ops.CharmBase]):
    # GIVEN a receive-otlp relation
    receiver = Relation(
        RECEIVE,
        remote_app_data={
            'rules': json.dumps({'logql': {}, 'promql': {}}),
            'metadata': '{}',
        },
    )
    state = State(leader=True, relations=[receiver])

    # AND WHEN any event executes the reconciler
    state_out = otlp_provider_ctx.run(otlp_provider_ctx.on.update_status(), state=state)
    local_app_data = next(iter(state_out.relations)).local_app_data

    # THEN otelcol offers its supported OTLP endpoints in the databag
    expected_endpoints = {
        'endpoints': [
            {
                'protocol': 'http',
                'endpoint': 'http://fqdn:4318',
                'telemetries': ['metrics'],
                'insecure': False,
            }
        ],
    }
    assert (actual_endpoints := json.loads(local_app_data.get('endpoints', '[]')))
    assert (
        _OtlpProviderAppData.model_validate({'endpoints': actual_endpoints}).model_dump()
        == expected_endpoints
    )


@pytest.mark.parametrize(
    'endpoints, expected_protocol',
    [
        # gRPC preferred over HTTP
        (
            [
                _OtlpEndpoint(
                    protocol='http', endpoint='http://host:4318', telemetries=['metrics']
                ),
                _OtlpEndpoint(
                    protocol='grpc', endpoint='http://host:4317', telemetries=['metrics']
                ),
            ],
            'grpc',
        ),
        # HTTP returned when gRPC is absent
        (
            [
                _OtlpEndpoint(
                    protocol='http', endpoint='http://host:4318', telemetries=['metrics']
                ),
            ],
            'http',
        ),
        # gRPC returned when HTTP is absent
        (
            [
                _OtlpEndpoint(
                    protocol='grpc', endpoint='http://host:4317', telemetries=['metrics']
                ),
            ],
            'grpc',
        ),
        # HTTP returned when new endpoint is present
        (
            [
                _OtlpEndpoint(
                    protocol='http', endpoint='http://host:4318', telemetries=['metrics']
                ),
                _OtlpEndpoint(
                    protocol='new', endpoint='http://host:4316', telemetries=['metrics']
                ),
            ],
            'http',
        ),
    ],
)
def test_favor_modern_endpoints(
    otlp_requirer_ctx: testing.Context[ops.CharmBase],
    endpoints: list[_OtlpEndpoint],
    expected_protocol: str,
):
    # GIVEN a list of endpoints
    state = State(leader=True)
    with otlp_requirer_ctx(otlp_requirer_ctx.on.update_status(), state=state) as mgr:
        # WHEN the requirer selects an endpoint
        requirer = OtlpRequirer(mgr.charm, SEND, PROTOCOLS, TELEMETRIES)

    # THEN the most modern one is chosen
    assert requirer._favor_modern_endpoints(endpoints).protocol == expected_protocol


def test_add_endpoint_insecure(otlp_requirer_ctx: testing.Context[ops.CharmBase]):
    state = State(leader=True)
    with otlp_requirer_ctx(otlp_requirer_ctx.on.update_status(), state=state) as mgr:
        # GIVEN a provider
        provider = OtlpProvider(mgr.charm)

    # WHEN insecure and secure endpoints are added
    provider.add_endpoint(
        protocol='http', endpoint='http://host:4318', telemetries=['metrics'], insecure=True
    ).add_endpoint(
        protocol='grpc', endpoint='http://host:4317', telemetries=['traces'], insecure=False
    )

    # THEN their security settings are preserved
    assert provider._endpoints == [
        _OtlpEndpoint(
            protocol='http',
            endpoint='http://host:4318',
            telemetries=['metrics'],
            insecure=True,
        ),
        _OtlpEndpoint(
            protocol='grpc',
            endpoint='http://host:4317',
            telemetries=['traces'],
            insecure=False,
        ),
    ]
