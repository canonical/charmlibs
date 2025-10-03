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
def null_state() -> ops.testing.State:
    update_cacerts_mock = ops.testing.Exec(('update-ca-certificates', '--fresh'))
    nginx_reload_mock = ops.testing.Exec(('nginx', '-s', 'reload'))
    return ops.testing.State(
        containers={
            ops.testing.Container(
                'nginx',
                can_connect=True,
                execs={update_cacerts_mock, nginx_reload_mock},
            ),
            ops.testing.Container('nginx-pexp', can_connect=True, execs={update_cacerts_mock}),
        }
    )


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
