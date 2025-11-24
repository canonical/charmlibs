# Copyright 2025 Canonical Ltd.
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

"""K8s charm for testing."""

import logging

from charmlibs.interfaces import temporal_worker_consumer
import common
import ops

logger = logging.getLogger(__name__)

CONTAINER = 'workload'


class Charm(common.Charm):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on[CONTAINER].pebble_ready, self._on_pebble_ready)
        self.temporal_worker_consumer_provider = temporal_worker_consumer.TemporalWorkerConsumerProvider(
            self,
        )

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
        """Handle pebble-ready event."""
        self.unit.status = ops.ActiveStatus()


if __name__ == '__main__':  # pragma: nocover
    ops.main(Charm)
