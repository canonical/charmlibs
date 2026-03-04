# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Feature: OTLP endpoint handling."""

import json
from typing import Any, cast
from unittest.mock import patch

import ops
import pytest
from ops import testing
from ops.testing import Relation, State
from pydantic import ValidationError

from charmlibs.otlp import OtlpEndpoint, OtlpProviderAppData

ALL_PROTOCOLS = ['grpc', 'http']
ALL_TELEMETRIES = ['logs', 'metrics', 'traces']
EMPTY_CONSUMER = {
    'rules': json.dumps({'logql': {}, 'promql': {}}),
    'metadata': json.dumps({}),
}

RECEIVE_OTLP = Relation('receive-otlp', remote_app_data=EMPTY_CONSUMER)


@pytest.mark.parametrize(
    'data, error_match',
    [
        (
            {'protocol': 'invalid', 'endpoint': 'http://host:4317', 'telemetries': ['logs']},
            "Input should be 'http' or 'grpc'",
        ),
        (
            {'protocol': 'grpc', 'endpoint': 'http://host:4317', 'telemetries': ['invalid']},
            "Input should be 'logs', 'metrics' or 'traces'",
        ),
    ],
)
def test_provider_app_data_raises_validation_error(data: dict[str, Any], error_match: str) -> None:
    """Test that OtlpProviderAppData validates protocols and telemetries."""
    with pytest.raises(ValidationError, match=error_match):
        OtlpProviderAppData(endpoints=[OtlpEndpoint(**data)])


# NOTE: we cannot use OtlpProviderAppData for "provides" since it would raise validation errors
@pytest.mark.parametrize(
    'provides, otlp_endpoint',
    (
        (
            # GIVEN an endpoint with an invalid protocol
            # * an endpoint with a valid protocol
            {
                'endpoints': json.dumps(
                    [
                        {
                            'protocol': 'fake',
                            'endpoint': 'http://host:0000',
                            'telemetries': ['metrics'],
                        },
                        {
                            'protocol': 'http',
                            'endpoint': 'http://host:4317',
                            'telemetries': ['metrics'],
                        },
                    ],
                ),
            },
            OtlpEndpoint(
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
                        'telemetries': ['logs', 'fake', 'traces'],
                    },
                ]),
            },
            OtlpEndpoint(
                protocol='http',
                endpoint='http://host:4317',
                telemetries=['logs', 'traces'],
            ),
        ),
        (
            # GIVEN a valid endpoint
            # * an invalid databag key
            {
                'endpoints': json.dumps(
                    [
                        {
                            'protocol': 'http',
                            'endpoint': 'http://host:4317',
                            'telemetries': ['metrics'],
                        }
                    ],
                ),
                'does_not': 'exist',
            },
            OtlpEndpoint(
                protocol='http',
                endpoint='http://host:4317',
                telemetries=['metrics'],
            ),
        ),
    ),
)
def test_send_otlp_invalid_databag(
    otlp_consumer_ctx: testing.Context[ops.CharmBase],
    provides: dict[str, Any],
    otlp_endpoint: OtlpEndpoint,
):
    # GIVEN a remote app provides an OtlpEndpoint
    # WHEN they are related over the "send-otlp" endpoint
    provider = Relation('send-otlp', id=123, remote_app_data=provides)
    state = State(relations=[provider], leader=True)

    with otlp_consumer_ctx(otlp_consumer_ctx.on.update_status(), state=state) as mgr:
        # WHEN the consumer processes the relation data
        # * the consumer supports all protocols and telemetries
        charm_any = cast('Any', mgr.charm)
        with (
            patch.object(charm_any.otlp_consumer, '_protocols', new=ALL_PROTOCOLS),
            patch.object(charm_any.otlp_consumer, '_telemetries', new=ALL_TELEMETRIES),
        ):
            # THEN the consumer does not raise an error
            # * the returned endpoint does not include invalid protocols or telemetries
            assert mgr.run()
            result = charm_any.otlp_consumer.endpoints[123]
            assert result.model_dump() == otlp_endpoint.model_dump()


@pytest.mark.parametrize(
    'protocols, telemetries, expected',
    [
        (
            ALL_PROTOCOLS,
            ALL_TELEMETRIES,
            {
                123: OtlpEndpoint(
                    protocol='http',
                    endpoint='http://provider-123.endpoint:4318',
                    telemetries=['logs', 'metrics'],
                ),
                456: OtlpEndpoint(
                    protocol='grpc',
                    endpoint='http://provider-456.endpoint:4317',
                    telemetries=['traces'],
                ),
            },
        ),
        (
            ['grpc'],
            ALL_TELEMETRIES,
            {
                456: OtlpEndpoint(
                    protocol='grpc',
                    endpoint='http://provider-456.endpoint:4317',
                    telemetries=['traces'],
                )
            },
        ),
        (
            ALL_PROTOCOLS,
            ['metrics'],
            {
                123: OtlpEndpoint(
                    protocol='http',
                    endpoint='http://provider-123.endpoint:4318',
                    telemetries=['metrics'],
                ),
                456: OtlpEndpoint(
                    protocol='http',
                    endpoint='http://provider-456.endpoint:4318',
                    telemetries=['metrics'],
                ),
            },
        ),
        (['http'], ['traces'], {}),
    ],
)
def test_send_otlp_with_varying_consumer_support(
    otlp_consumer_ctx: testing.Context[ops.CharmBase],
    protocols: list[str],
    telemetries: list[str],
    expected: dict[int, OtlpEndpoint],
):
    # GIVEN a remote app provides multiple OtlpEndpoints
    remote_app_data_1 = {
        'endpoints': json.dumps([
            {
                'protocol': 'http',
                'endpoint': 'http://provider-123.endpoint:4318',
                'telemetries': ['logs', 'metrics'],
            }
        ])
    }
    remote_app_data_2 = {
        'endpoints': json.dumps([
            {
                'protocol': 'grpc',
                'endpoint': 'http://provider-456.endpoint:4317',
                'telemetries': ['traces'],
            },
            {
                'protocol': 'http',
                'endpoint': 'http://provider-456.endpoint:4318',
                'telemetries': ['metrics'],
            },
        ])
    }

    # WHEN they are related over the "send-otlp" endpoint
    provider_0 = Relation(
        'send-otlp',
        id=123,
        remote_app_data=remote_app_data_1,
    )
    provider_1 = Relation(
        'send-otlp',
        id=456,
        remote_app_data=remote_app_data_2,
    )
    state = State(
        relations=[provider_0, provider_1],
        leader=True,
    )

    # AND WHEN the consumer has varying support for OTLP protocols and telemetries
    with otlp_consumer_ctx(otlp_consumer_ctx.on.update_status(), state=state) as mgr:
        charm_any = cast('Any', mgr.charm)
        with (
            patch.object(charm_any.otlp_consumer, '_protocols', new=protocols),
            patch.object(charm_any.otlp_consumer, '_telemetries', new=telemetries),
        ):
            remote_endpoints = charm_any.otlp_consumer.endpoints

    # THEN the returned endpoints are filtered accordingly
    assert {k: v.model_dump() for k, v in remote_endpoints.items()} == {
        k: v.model_dump() for k, v in expected.items()
    }


def test_send_otlp(otlp_consumer_ctx: testing.Context[ops.CharmBase]):
    # GIVEN a remote app provides multiple OtlpEndpoints
    remote_app_data_1 = {
        'endpoints': json.dumps([
            {
                'protocol': 'http',
                'endpoint': 'http://provider-123.endpoint:4318',
                'telemetries': ['logs', 'metrics'],
            }
        ])
    }
    remote_app_data_2 = {
        'endpoints': json.dumps([
            {
                'protocol': 'grpc',
                'endpoint': 'http://provider-456.endpoint:4317',
                'telemetries': ['traces'],
            },
            {
                'protocol': 'http',
                'endpoint': 'http://provider-456.endpoint:4318',
                'telemetries': ['metrics'],
            },
        ])
    }

    expected_endpoints = {
        456: OtlpEndpoint(
            protocol='http',
            endpoint='http://provider-456.endpoint:4318',
            telemetries=['metrics'],
        ),
        123: OtlpEndpoint(
            protocol='http',
            endpoint='http://provider-123.endpoint:4318',
            telemetries=['logs', 'metrics'],
        ),
    }

    # WHEN they are related over the "send-otlp" endpoint
    provider_1 = Relation(
        'send-otlp',
        id=123,
        remote_app_data=remote_app_data_1,
    )
    provider_2 = Relation(
        'send-otlp',
        id=456,
        remote_app_data=remote_app_data_2,
    )
    state = State(
        relations=[provider_1, provider_2],
        leader=True,
    )

    # AND WHEN otelcol supports a subset of OTLP protocols and telemetries
    with otlp_consumer_ctx(otlp_consumer_ctx.on.update_status(), state=state) as mgr:
        charm_any = cast('Any', mgr.charm)
        remote_endpoints = charm_any.otlp_consumer.endpoints

    # THEN the returned endpoints are filtered accordingly
    assert {k: v.model_dump() for k, v in remote_endpoints.items()} == {
        k: v.model_dump() for k, v in expected_endpoints.items()
    }


def test_receive_otlp(otlp_provider_ctx: testing.Context[ops.CharmBase]):
    # GIVEN a receive-otlp relation
    state = State(
        leader=True,
        relations=[RECEIVE_OTLP],
    )

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
            }
        ],
    }
    assert (actual_endpoints := json.loads(local_app_data.get('endpoints', '[]')))
    assert (
        OtlpProviderAppData.model_validate({'endpoints': actual_endpoints}).model_dump()
        == expected_endpoints
    )
