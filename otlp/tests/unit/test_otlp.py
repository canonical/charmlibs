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

from charmlibs.otlp import (
    OtlpEndpoint,
    OtlpProviderAppData,
)

APP_DATA = {
    OtlpProviderAppData.KEY: (
        '{"endpoints": ['
        '{"protocol": "grpc", '
        '"endpoint": "http://host:4317", '
        '"telemetries": ["logs"]}'
        ']}'
    )
}

ALL_PROTOCOLS = ['grpc', 'http']
ALL_TELEMETRIES = ['logs', 'metrics', 'traces']


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
def test_provider_app_data_raises_validation_error_lib(
    data: dict[str, Any], error_match: str
) -> None:
    """Test that OtlpProviderAppData validates protocols and telemetries."""
    with pytest.raises(ValidationError, match=error_match):
        OtlpProviderAppData(endpoints=[OtlpEndpoint(**data)])


# NOTE: we cannot use OtlpProviderAppData for "provides" since it would raise validation errors
@pytest.mark.parametrize(
    'provides, otlp_endpoint',
    (
        (
            {
                'endpoints': [
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
                ]
            },
            OtlpEndpoint(
                protocol='http',
                endpoint='http://host:4317',
                telemetries=['metrics'],
            ),
        ),
        (
            {
                'endpoints': [
                    {
                        'protocol': 'http',
                        'endpoint': 'http://host:4317',
                        'telemetries': ['logs', 'fake', 'traces'],
                    },
                ]
            },
            OtlpEndpoint(
                protocol='http',
                endpoint='http://host:4317',
                telemetries=['logs', 'traces'],
            ),
        ),
    ),
)
def test_send_otlp_invalid_lib(
    otlp_consumer_ctx: testing.Context[ops.CharmBase],
    provides: dict[str, Any],
    otlp_endpoint: OtlpEndpoint,
) -> None:
    # GIVEN a remote app provides an invalid OtlpEndpoint
    # WHEN they are related over the "send-otlp" endpoint
    provider = Relation(
        'send-otlp',
        id=123,
        remote_app_data={OtlpProviderAppData.KEY: json.dumps(provides)},
    )
    state = State(
        relations=[provider],
        leader=True,
    )

    with otlp_consumer_ctx(otlp_consumer_ctx.on.update_status(), state=state) as mgr:
        mgr.run()
        # AND WHEN the consumer supports all telemetries
        with (
            patch.object(cast('Any', mgr.charm).otlp_consumer, '_protocols', new=ALL_PROTOCOLS),
            patch.object(
                cast('Any', mgr.charm).otlp_consumer, '_telemetries', new=ALL_TELEMETRIES
            ),
        ):
            result = cast(
                'OtlpEndpoint',
                cast('Any', mgr.charm).otlp_consumer.get_remote_otlp_endpoints()[123],
            )

    # THEN the returned endpoint does not include invalid protocols or telemetries
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
def test_send_otlp_with_varying_consumer_support_lib(
    otlp_consumer_ctx: testing.Context[ops.CharmBase],
    protocols: list[str],
    telemetries: list[str],
    expected: dict[int, OtlpEndpoint],
) -> None:
    # GIVEN a remote app provides multiple OtlpEndpoints
    remote_app_data_1 = {
        OtlpProviderAppData.KEY: json.dumps(
            OtlpProviderAppData(
                endpoints=[
                    OtlpEndpoint(
                        protocol='http',
                        endpoint='http://provider-123.endpoint:4318',
                        telemetries=['logs', 'metrics'],
                    )
                ]
            ).model_dump()
        )
    }
    remote_app_data_2 = {
        OtlpProviderAppData.KEY: json.dumps(
            OtlpProviderAppData(
                endpoints=[
                    OtlpEndpoint(
                        protocol='grpc',
                        endpoint='http://provider-456.endpoint:4317',
                        telemetries=['traces'],
                    ),
                    OtlpEndpoint(
                        protocol='http',
                        endpoint='http://provider-456.endpoint:4318',
                        telemetries=['metrics'],
                    ),
                ]
            ).model_dump()
        )
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
        with (
            patch.object(cast('Any', mgr.charm).otlp_consumer, '_protocols', new=protocols),
            patch.object(cast('Any', mgr.charm).otlp_consumer, '_telemetries', new=telemetries),
        ):
            remote_endpoints = cast(
                'dict[int, OtlpEndpoint]',
                cast('Any', mgr.charm).otlp_consumer.get_remote_otlp_endpoints(),
            )

    # THEN the returned endpoints are filtered accordingly
    assert {k: v.model_dump() for k, v in remote_endpoints.items()} == {
        k: v.model_dump() for k, v in expected.items()
    }
