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

"""Example requirer charm for unit tests.

Wraps a single tracing endpoint (``limit: 1``), which is the common case and the one the
library's ``get_endpoint`` is easiest to use with. See requirer_charm_multi.py for a charm
whose endpoint carries several providers.
"""

from __future__ import annotations

import ops

from charmlibs.interfaces import tracing

META = {
    'name': 'requirer',
    'requires': {
        'tracing': {'interface': 'tracing', 'limit': 1},
        # A second, unrelated endpoint, so that tests can check the rest of the state is
        # preserved. ops.testing rejects a relation whose endpoint isn't in the metadata.
        'other-endpoint': {'interface': 'something-else'},
    },
}
PROTOCOLS: list[tracing.ReceiverProtocol] = ['otlp_http', 'zipkin']


class RequirerCharm(ops.CharmBase):
    """A minimal requirer charm for testing the tracing interface."""

    endpoints: dict[tracing.ReceiverProtocol, str] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.tracing = tracing.TracingEndpointRequirer(self, protocols=PROTOCOLS)
        framework.observe(self.on.update_status, self._reconcile)
        # endpoint_changed is emitted on every relation-changed that finds usable data --
        # it is level-triggered, not a change signal -- so the handler reconciles against
        # what it can read rather than treating each event as news.
        framework.observe(self.tracing.on.endpoint_changed, self._reconcile)
        framework.observe(self.tracing.on.endpoint_removed, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        if not self.tracing.is_ready():
            self.endpoints = None
            self.unit.status = ops.BlockedStatus('tracing not available')
            return
        # imagine we configure a workload with these
        endpoints: dict[tracing.ReceiverProtocol, str] = {}
        for protocol in PROTOCOLS:
            url = self.tracing.get_endpoint(protocol)
            if url is not None:
                endpoints[protocol] = url
        self.endpoints = endpoints
        if len(endpoints) != len(PROTOCOLS):
            missing = sorted(p for p in PROTOCOLS if p not in endpoints)
            self.unit.status = ops.BlockedStatus(f'no receiver for {missing}')
            return
        self.unit.status = ops.ActiveStatus('tracing ready')
