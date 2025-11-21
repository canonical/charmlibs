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

from typing import Any

from ops.charm import CharmBase
from ops.main import main
from scenario import ActiveStatus

from charmlibs.interfaces.temporal_worker_consumer import TemporalWorkerConsumerRequirer


class DummyWorkerConsumerRequirerCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.worker_consumer = TemporalWorkerConsumerRequirer(self)
        self.framework.observe(
            self.worker_consumer.on.worker_consumer_available, self._on_worker_consumer_available
        )

    def _on_worker_consumer_available(self, event: Any) -> None:
        namespace = self.worker_consumer.namespace
        queue = self.worker_consumer.queue
        self.unit.status = ActiveStatus(f'Namespace: {namespace}, Queue: {queue}')


if __name__ == '__main__':
    main(DummyWorkerConsumerRequirerCharm)
