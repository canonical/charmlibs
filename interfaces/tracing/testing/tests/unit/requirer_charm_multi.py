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

"""Example requirer charm whose tracing endpoint has no ``limit``.

Several providers may be related on the one endpoint, so every library call names the
relation it means -- ``TracingEndpointRequirer`` raises ``AmbiguousRelationUsageError``
otherwise. Exists so that tests can show one remote per related application.
"""

from __future__ import annotations

import ops

from charmlibs.interfaces import tracing

META = {
    'name': 'requirer-multi',
    'requires': {'tracing': {'interface': 'tracing'}},
}
PROTOCOL: tracing.ReceiverProtocol = 'otlp_http'


class MultiRequirerCharm(ops.CharmBase):
    """A requirer charm that collects an endpoint from every provider it is related to."""

    endpoints: dict[str, str] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.tracing = tracing.TracingEndpointRequirer(self, protocols=[PROTOCOL])
        framework.observe(self.on.update_status, self._reconcile)
        framework.observe(self.tracing.on.endpoint_changed, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        endpoints: dict[str, str] = {}
        for relation in self.tracing.relations:
            if not self.tracing.is_ready(relation):
                continue
            url = self.tracing.get_endpoint(PROTOCOL, relation=relation)
            if url is not None:
                endpoints[relation.app.name] = url
        self.endpoints = endpoints or None
        self.unit.status = ops.ActiveStatus(f'{len(endpoints)} tracing backend(s)')
