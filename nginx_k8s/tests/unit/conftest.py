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

from __future__ import annotations

import ops.testing
import pytest


@pytest.fixture
def nginx_container():
    return ops.testing.Container(
        'nginx',
        can_connect=True,
        execs={
            ops.testing.Exec(['update-ca-certificates', '--fresh'], return_code=0),
            ops.testing.Exec(('nginx', '-s', 'reload')),
        },
    )


@pytest.fixture
def nginx_prometheus_exporter_container():
    return ops.testing.Container(
        'nginx-pexp',
        can_connect=True,
    )


@pytest.fixture
def null_state(nginx_prometheus_exporter_container, nginx_container) -> ops.testing.State:
    return ops.testing.State(containers={nginx_container, nginx_prometheus_exporter_container})


@pytest.fixture
def ctx() -> ops.testing.Context[ops.CharmBase]:
    return ops.testing.Context(
        ops.CharmBase,
        meta={
            'name': 'tony',
            'containers': {
                'nginx': {},
                'nginx-pexp': {},
            },
        },
    )
