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

"""OTLP Provider and Requirer Library.

OTLP is a general-purpose telemetry data delivery protocol defined by
`the design goals <https://github.com/open-telemetry/opentelemetry-proto/blob/main/docs/design-goals.md>`_
and
`requirements <https://github.com/open-telemetry/opentelemetry-proto/blob/main/docs/requirements.md>`_
of the project.

This library provides a way for charms to share OTLP endpoint information, and associated Loki and
Prometheus rules. This library requires that the charm's workload already supports
sending/receiving OTLP data and focuses on communicating those endpoints.

Getting Started
===============

Provider Side (Charms offering OTLP endpoints)
-----------------------------------------------

To provide OTLP endpoints, use the ``OtlpProvider`` class. Configure and send endpoints with the
``add_endpoint`` and ``publish()`` methods::

    from charmlibs.interfaces.otlp import OtlpProvider

    class MyOtlpServer(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.framework.observe(self.on.ingress_ready, self._publish_endpoints)

        def _publish_endpoints(self, event):
            OtlpProvider(self).add_endpoint(
                protocol="grpc",
                endpoint="https://my-app.ingress:4317",
                telemetries=["logs", "metrics"],
            ).add_endpoint(
                protocol="http",
                endpoint="https://my-app.ingress:4318",
                telemetries=["traces"],
            ).publish()

Providers add endpoints explicitly; nothing is auto-published by default. Make sure to add
endpoints and publish them after the charm's endpoint details have been updated e.g., ingress or
TLS changes.

The OtlpProvider also consumes rules from related OtlpRequirer charms, which can be retrieved with
the ``rules`` property::

    from charmlibs.interfaces.otlp import OtlpProvider

    class MyOtlpServer(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.framework.observe(self.on.update_status, self._access_rules)

        def _access_rules(self, event):
            for relation_id, rule_store in OtlpProvider(self).rules.items():
                pass  # do something with rule_store.logql and/or rule_store.promql

Requirer Side (Charms requiring OTLP endpoints)
-----------------------------------------------

To consume OTLP endpoints, use the ``OtlpRequirer`` class. The OTLP sender may only support a
subset of protocols and telemetries, which can be configured at instantiation::

    from charmlibs.interfaces.otlp import OtlpRequirer

    class MyOtlpSender(CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.framework.observe(self.on.update_status, self._access_endpoints)

        def _access_endpoints(self, _: ops.EventBase):
            OtlpRequirer(
                self,
                protocols=["grpc", "http"],
                telemetries=["logs", "metrics", "traces"],
            ).endpoints

Given the defined, supported protocols and telemetries, the OtlpRequirer will filter out
unsupported endpoints and prune unsupported telemetries. After filtering, requirer selection
condenses the list to a single endpoint per relation.
Endpoints with modern protocols are favoured over legacy ones.
That means an endpoint supporting the `gRPC` protocol will be selected over one supporting `HTTP`.
Unknown protocols will receive the lowest priority.

The OtlpRequirer also publishes user-defined and generic (applied to all charms) rules to related
OtlpProvider charms with the ``publish()`` method::

    from charmlibs.interfaces.otlp import OtlpRequirer, RulesStore

    class MyOtlpSender(CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.framework.observe(self.on.update_status, self._publish_rules)

        def _publish_rules(self, _: ops.EventBase):
            rules = (
                RuleStore(JujuTopology.from_charm(self))
                .add_logql(SINGLE_LOGQL_ALERT, group_name='test_logql_alert')
                .add_promql(SINGLE_PROMQL_RECORD, group_name='test_promql_record')
                .add_logql(OFFICIAL_LOGQL_RULES)
            )
            OtlpRequirer(self, rules=rules).publish()

Generic rules are sourced from `cosl.rules.generic_alert_groups <https://github.com/canonical/cos-lib/blob/main/src/cosl/rules.py>`_.
If the charm is an aggregator e.g., opentelemetry-collector, the type of generic rules to be
injected into the charm's RuleStore should reflect that. This is configurable by setting the
``aggregator_peer_relation_name`` with the name of the charm's peer relation::

    OtlpRequirer(..., aggregator_peer_relation_name="my-peers").publish()

Pebble Log Forwarding (K8s charms)
-----------------------------------

For Kubernetes charms that use Pebble, ``PebbleLogForwarder`` builds a Pebble layer that
configures `log forwarding <https://documentation.ubuntu.com/pebble/reference/log-forwarding/>`_
to OTLP endpoints using Pebble's ``opentelemetry`` log target type.

Only endpoints whose ``telemetries`` include ``"logs"`` are forwarded.
This class is a K8s-only utility; machine charms should configure log forwarding through
their own mechanism::

    from charmlibs.interfaces.otlp import OtlpRequirer, PebbleLogForwarder
    from cosl.juju_topology import JujuTopology

    class MyK8sCharm(CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.framework.observe(
                self.on["mycontainer"].pebble_ready, self._configure_logging
            )

        def _configure_logging(self, event: ops.PebbleReadyEvent):
            otlp_endpoints = OtlpRequirer(
                self, protocols=["http"], telemetries=["logs"],
            ).endpoints
            layer = PebbleLogForwarder.build_otlp_layer(
                otlp_endpoints,
                topology=JujuTopology.from_charm(self),
            )
            event.workload.add_layer(
                f"{event.workload.name}-log-forwarding", layer, combine=True,
            )

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

The OtlpRequirer offers compressed rules in the relation databag under the ``rules`` key, which
have this structure when decompressed::

    "rules": {
        "promql": {...},
        "logql": {...},
    }

The charm's metadata is included under the ``metadata`` key for the provider to know the source of
the rules::

    "metadata": {
        "model": "my-model",
        "model_uuid": "f4d59020-c8e7-4053-8044-a2c1e5591c7f",
        "application": "my-app",
        "charm_name": "my-charm",
        "unit": "my-charm/0",
    }
"""

from ._log_forwarder import PebbleLogForwarder
from ._otlp import (
    OtlpEndpoint,
    OtlpProvider,
    OtlpRequirer,
    RuleStore,
)
from ._version import __version__ as __version__

__all__ = [
    # only the names listed in __all__ are imported when executing:
    # from charmlibs.interfaces.otlp import *
    'OtlpEndpoint',
    'OtlpProvider',
    'OtlpRequirer',
    'PebbleLogForwarder',
    'RuleStore',
]
