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

"""Tests of behaviour that charm unit tests rely on, using the mock Pebble from ops.testing."""

from __future__ import annotations

import typing

import ops
import ops.testing
import pytest

from charmlibs.pathops import ContainerPath

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

pytestmark = pytest.mark.filterwarnings('ignore:Harness is deprecated')


@pytest.fixture
def harness() -> Iterator[ops.testing.Harness[ops.CharmBase]]:
    harness = ops.testing.Harness(ops.CharmBase, meta='{name: charm, containers: {c: {}}}')
    harness.begin()
    harness.set_can_connect('c', True)
    yield harness
    harness.cleanup()


@pytest.fixture
def container(harness: ops.testing.Harness[ops.CharmBase]) -> ops.Container:
    return harness.model.unit.get_container('c')


@pytest.fixture
def root(harness: ops.testing.Harness[ops.CharmBase]) -> pathlib.Path:
    return harness.get_filesystem_root('c')


@pytest.mark.parametrize('name', ('s*', 's?bling', '[s]ibling', 'sibling[', 'back\\slash'))
def test_name_isnt_a_pattern(container: ops.Container, root: pathlib.Path, name: str):
    (root / 'sibling').touch()
    path = ContainerPath('/', name, container=container)
    with pytest.raises(FileNotFoundError):
        path.unlink()
    (root / name).touch()
    path.unlink()
    assert (root / 'sibling').exists()
