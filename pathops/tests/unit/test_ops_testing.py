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

"""Tests of behaviour that charm unit tests rely on, using the mock Pebble from ops.testing.

Harness and Scenario share the same mock Pebble filesystem, so each test runs against both.
"""

from __future__ import annotations

import dataclasses
import json
import typing

import ops
import ops.testing
import pytest

from charmlibs.pathops import ContainerPath

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

pytestmark = pytest.mark.filterwarnings('ignore:Harness is deprecated')

META: dict[str, typing.Any] = {'name': 'charm', 'containers': {'c': {}}}


@dataclasses.dataclass
class MockContainer:
    container: ops.Container
    root: pathlib.Path  # local directory holding the files under `base` in the container
    base: str


@pytest.fixture(params=['harness', 'scenario'])
def mock(request: pytest.FixtureRequest, tmp_path: pathlib.Path) -> Iterator[MockContainer]:
    if request.param == 'harness':
        harness = ops.testing.Harness(ops.CharmBase, meta=json.dumps(META))
        harness.begin()
        harness.set_can_connect('c', True)
        yield MockContainer(
            harness.model.unit.get_container('c'), harness.get_filesystem_root('c'), '/'
        )
        harness.cleanup()
        return
    ctx = ops.testing.Context(ops.CharmBase, meta=META)
    mount = ops.testing.Mount(location='/data', source=tmp_path)
    container = ops.testing.Container('c', can_connect=True, mounts={'data': mount})
    with ctx(ctx.on.update_status(), ops.testing.State(containers={container})) as manager:
        yield MockContainer(manager.charm.unit.get_container('c'), tmp_path, '/data')


@pytest.mark.parametrize('name', ('s*', 's?bling', '[s]ibling', 'sibling[', 'back\\slash'))
def test_name_isnt_a_pattern(mock: MockContainer, name: str):
    (mock.root / 'sibling').touch()
    path = ContainerPath(mock.base, name, container=mock.container)
    with pytest.raises(FileNotFoundError):
        path.unlink()
    (mock.root / name).touch()
    path.unlink()
    assert (mock.root / 'sibling').exists()
