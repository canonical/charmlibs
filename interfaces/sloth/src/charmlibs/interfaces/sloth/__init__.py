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

r"""SLO Provider and Requirer Library.

This library provides a way for charms to share SLO (Service Level Objective)
specifications with the Sloth charm, which will convert them into Prometheus
recording and alerting rules.

Getting Started
===============

Provider Side (Charms providing SLO specs)
-------------------------------------------

To provide SLO specifications to Sloth, use the ``SLOProvider`` class.
The recommended approach is to allow users to configure SLOs via ``juju config``::

    from charmlibs.interfaces.sloth import SLOProvider

    class MyCharm(ops.CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.slo_provider = SLOProvider(self)
            self.framework.observe(self.on.config_changed, self._on_config_changed)

        def _on_config_changed(self, event):
            # Read SLO configuration from juju config
            slo_config = self.config.get('slo_config', '')
            if slo_config:
                self.slo_provider.provide_slos(slo_config)

Users can then configure SLOs using ``juju config``::

    juju config my-app slo_config='
    version: prometheus/v1
    service: my-service
    labels:
      team: my-team
    slos:
      - name: requests-availability
        objective: 99.9
        description: "99.9% of requests should succeed"
        sli:
          events:
            error_query: '\''sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))'\''
            total_query: '\''sum(rate(http_requests_total[{{.window}}]))'\''
        alerting:
          name: MyServiceHighErrorRate
          labels:
            severity: critical
    '

To specify multiple SLOs for different services, separate them with YAML document
separators (``---``).

Requirer Side (Sloth charm)
----------------------------

The Sloth charm uses ``SLORequirer`` to collect SLO specifications.
Validation is performed on the requirer side::

    from charmlibs.interfaces.sloth import SLORequirer

    class SlothCharm(ops.CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.slo_requirer = SLORequirer(self)

        def _on_config_changed(self, event):
            # Get validated SLO specs from all related charms
            slos = self.slo_requirer.get_slos()
            # Process SLOs and generate rules

Relation Data Format
====================

SLO specifications are stored in the relation databag as YAML strings under the
``slo_spec`` key. Each provider unit can provide one or more SLO specifications.

For a single service::

    slo_spec: |
      version: prometheus/v1
      service: my-service
      labels:
        team: my-team
      slos:
        - name: requests-availability
          objective: 99.9
          description: "99.9% of requests should succeed"
          sli:
            events:
              error_query: 'sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))'
              total_query: 'sum(rate(http_requests_total[{{.window}}]))'
          alerting:
            name: MyServiceHighErrorRate
            labels:
              severity: critical

For multiple services (separated by YAML document separators)::

    slo_spec: |
      version: prometheus/v1
      service: my-service
      slos:
        - name: requests-availability
          objective: 99.9
      ---
      version: prometheus/v1
      service: my-other-service
      slos:
        - name: requests-latency
          objective: 99.5
"""

from ._sloth import (
    SLOError,
    SLOProvider,
    SLORequirer,
    SLOSpec,
    SLOValidationError,
)
from ._topology import inject_topology_labels
from ._version import __version__ as __version__

__all__ = [
    'SLOError',
    'SLOProvider',
    'SLORequirer',
    'SLOSpec',
    'SLOValidationError',
    'inject_topology_labels',
]
