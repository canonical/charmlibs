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

from pathlib import Path
from typing import Any

import pytest
import yaml
from ops import testing

from dummy_requirer.src.charm import DummyWorkerConsumerRequirerCharm

METADATA: dict[str, Any] = yaml.safe_load(
    (Path(__file__).parent / 'dummy_requirer' / 'charmcraft.yaml').read_text()
)


class TestTemporalWorkerConsumerRequirer:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = testing.Context(
            charm_type=DummyWorkerConsumerRequirerCharm,
            meta=METADATA,
        )

    def test_require(self):
        relation = testing.Relation(
            endpoint='temporal-worker-consumer',
            interface='temporal-worker-consumer',
            remote_app_name='temporal-worker-consumer-interface-provider',
            remote_app_data={
                'namespace': 'test-namespace',
                'queue': 'test-queue',
            },
        )
        state_in = testing.State(relations={relation})
        state_out = self.ctx.run(self.ctx.on.relation_changed(relation), state_in)
        assert state_out.unit_status == testing.ActiveStatus(
            'Namespace: test-namespace, Queue: test-queue'
        )
