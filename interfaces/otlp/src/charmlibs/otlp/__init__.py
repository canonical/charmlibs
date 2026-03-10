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

"""OTLP Provider and Consumer Library.

OTLP is a general-purpose telemetry data delivery protocol defined by
[the design goals of the project]
(https://github.com/open-telemetry/opentelemetry-proto/blob/main/docs/design-goals.md)
and
[requirements](https://github.com/open-telemetry/opentelemetry-proto/blob/main/docs/requirements.md).

This library provides a way for charms to share OTLP endpoint information and associated Loki and
Prometheus rules. This library requires that the charm's workload already supports
sending/receiving OTLP data and focuses on communicating those endpoints.

Getting Started
===============

Provider Side (Charms offering OTLP endpoints)
----------------------------------------------

To provide OTLP endpoints, use the ``OtlpProvider`` class. Configure and send endpoints with the
``add_endpoint`` and ``publish()`` methods::

    from charmlibs.interfaces.otlp import OtlpProvider

    class MyOtlpServer(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.otlp_provider = OtlpProvider(self)
            self.framework.observe(self.on.ingress_ready, self._on_ingress_ready)

        def _on_ingress_ready(self, event):
            self.otlp_provider.add_endpoint(
                    protocol="grpc",
                    endpoint="https://my-app.ingress:4317",
                    telemetries=["logs", "metrics"],
            )
            self.otlp_provider.add_endpoint(
                    protocol="http",
                    endpoint="https://my-app.ingress:4318",
                    telemetries=["traces"],
            )
            self.otlp_provider.publish()

Providers add endpoints explicitly; nothing is auto-published by default. Make sure to add
endpoints and publish them after the charm's endpoint details have been updated e.g., ingress or
TLS changes.

The OtlpProvider also consumes rules from related OtlpConsumer charms, which can be retrieved with
the ``rules()`` method::
    # snip ...
    promql_rules = self.otlp_provider.rules("promql")
    logql_rules = self.otlp_provider.rules("logql")

Consumer Side (Charms consuming OTLP endpoints)
---------------------------------------------

To consume OTLP endpoints, use the ``OtlpConsumer`` class. The OTLP sender may only support a
subset of protocols and telemetries, which can be configured at instantiation::

    from charmlibs.interfaces.otlp import OtlpConsumer

    class MyOtlpSender(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.otlp_consumer = OtlpConsumer(
                self,
                protocols=["grpc", "http"],
                telemetries=["logs", "metrics", "traces"],
                loki_rules_path="./src/loki_alert_rules",
                prometheus_rules_path="./src/prometheus_alert_rules",
            )
            self.framework.observe(self.on.update_status, self._reconcile)

        def _reconcile(self, event):
            supported_endpoints = self.otlp_consumer.endpoints

Given the defined, supported protocols and telemetries, the OtlpConsumer will filter out
unsupported endpoints and prune unsupported telemetries. After filtering, consumer selection
condenses the list to a single endpoint per relation.

The OtlpConsumer also publishes rules to related OtlpProvider charms with the ``publish()``
method::
    # snip ...
    self.otlp_consumer.publish()

It is the charm's responsibility to manage the rules in the ``loki_rules_path`` and
``prometheus_rules_path`` directories, which will be forwarded to the related OtlpProvider charms.

Relation Data Format
====================

The OtlpProvider offers a list of OTLP endpoints in the relation databag under the ``endpoints``
key. Each provider may offer any number of OTLP endpoints::

    "endpoints": [
        {
            "protocol": "grpc",
            "endpoint": "https://my-app.ingress:4317",
            "telemetries": ["logs", "metrics"],
        },
        {
            "protocol": "http",
            "endpoint": "https://my-app.ingress:4318",
            "telemetries": ["traces"],
        },
    ]

The OtlpConsumer offers compressed rules in the relation databag under the ``rules`` key. The
charm's metadata is included under the ``metadata`` key for the provider to know the source of the
rules::

    "rules": {
        "promql": {...},
        "logql": {...},
    }
    "metadata": {
        "model": "my-model",
        "model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
        "application": "my-app",
        "charm": "my-charm",
        "unit": "my-charm/0",
    }
"""

from ._otlp import (
    OtlpConsumer,
    OtlpConsumerAppData,
    OtlpEndpoint,
    OtlpProvider,
    OtlpProviderAppData,
    RulesModel,
)
from ._version import __version__ as __version__

__all__ = [
    # only the names listed in __all__ are imported when executing:
    # from charmlibs.otlp import *
    'OtlpConsumer',
    'OtlpConsumerAppData',
    'OtlpEndpoint',
    'OtlpProvider',
    'OtlpProviderAppData',
    'RulesModel',
]
