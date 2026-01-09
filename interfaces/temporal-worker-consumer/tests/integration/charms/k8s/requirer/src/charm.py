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

import common
import ops

from charmlibs.interfaces import temporal_worker_consumer

logger = logging.getLogger(__name__)

CONTAINER = 'workload'


class Charm(common.Charm):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on[CONTAINER].pebble_ready, self._configure)
        self.worker_consumer = temporal_worker_consumer.TemporalWorkerConsumerRequirer(self)
        framework.observe(
            self.worker_consumer.on.temporal_worker_consumer_available, self._configure
        )

    def _configure(self, event: ops.EventBase):
        """Handle pebble-ready event."""
        if self.worker_consumer.namespace is None or self.worker_consumer.queue is None:
            self.unit.status = ops.ActiveStatus(
                'Waiting for temporal-worker-consumer relation data'
            )
            return
        self.unit.status = ops.ActiveStatus(
            f'Namespace: {self.worker_consumer.namespace}, Queue: {self.worker_consumer.queue}'
        )


if __name__ == '__main__':  # pragma: nocover
    ops.main(Charm)
