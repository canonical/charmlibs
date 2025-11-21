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

from dummy_provider.src.charm import DummyWorkerConsumerProviderCharm

METADATA: dict[str, Any] = yaml.safe_load(
    (Path(__file__).parent / 'dummy_provider' / 'charmcraft.yaml').read_text()
)


class TestTemporalWorkerConsumerProvider:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = testing.Context(
            charm_type=DummyWorkerConsumerProviderCharm, meta=METADATA, config=METADATA['config']
        )

    def test_provides(self):
        relation = testing.Relation(
            endpoint='temporal-worker-consumer',
            interface='temporal-worker-consumer',
            remote_app_name='temporal-worker-consumer-interface-requirer',
        )
        state_in = testing.State(
            relations={relation},
            config={'namespace': 'test-namespace', 'queue': 'test-queue'},
            leader=True,
        )
        state_out = self.ctx.run(self.ctx.on.relation_changed(relation), state_in)
        for r in state_out.relations:
            if r.id == relation.id:
                assert r.local_app_data == {
                    'namespace': 'test-namespace',
                    'queue': 'test-queue',
                }

    def test_provides_config_changed(self):
        relation = testing.Relation(
            endpoint='temporal-worker-consumer',
            interface='temporal-worker-consumer',
            remote_app_name='temporal-worker-consumer-interface-requirer',
        )
        state_in = testing.State(
            relations={relation},
            config={'namespace': 'initial-namespace', 'queue': 'initial-queue'},
            leader=True,
        )
        # Initial relation changed to set data
        state_intermediate = self.ctx.run(self.ctx.on.relation_changed(relation), state_in)
        # Now change config
        state_updated = testing.State(
            relations=state_intermediate.relations,
            config={'namespace': 'updated-namespace', 'queue': 'updated-queue'},
            leader=True,
        )

        state_out = self.ctx.run(self.ctx.on.config_changed(), state_updated)
        for r in state_out.relations:
            if r.id == relation.id:
                assert r.local_app_data == {
                    'namespace': 'updated-namespace',
                    'queue': 'updated-queue',
                }
