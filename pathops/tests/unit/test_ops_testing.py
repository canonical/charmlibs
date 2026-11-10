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

# The container's mount point for the test's temporary directory.
MOUNT = '/data'


@pytest.fixture
def container(tmp_path: pathlib.Path) -> Iterator[ops.Container]:
    """A container whose files under MOUNT are in tmp_path, during a Scenario event."""
    ctx = ops.testing.Context(ops.CharmBase, meta={'name': 'charm', 'containers': {'c': {}}})
    mount = ops.testing.Mount(location=MOUNT, source=tmp_path)
    state = ops.testing.State(
        containers={ops.testing.Container('c', can_connect=True, mounts={'data': mount})}
    )
    with ctx(ctx.on.update_status(), state) as manager:
        yield manager.charm.unit.get_container('c')


@pytest.mark.parametrize('name', ('s*', 's?bling', '[s]ibling', 'sibling[', 'back\\slash'))
def test_name_isnt_a_pattern(container: ops.Container, tmp_path: pathlib.Path, name: str):
    (tmp_path / 'sibling').touch()
    path = ContainerPath(MOUNT, name, container=container)
    with pytest.raises(FileNotFoundError):
        path.unlink()
    (tmp_path / name).touch()
    path.unlink()
    assert (tmp_path / 'sibling').exists()


@pytest.mark.parametrize('name', ('s*', 's?bling', '[s]ibling', 'sibling[', 'back\\slash'))
def test_is_symlink_name_isnt_a_pattern(
    container: ops.Container, tmp_path: pathlib.Path, name: str
):
    (tmp_path / 'sibling').symlink_to(tmp_path)
    path = ContainerPath(MOUNT, name, container=container)
    assert not path.is_symlink()
    (tmp_path / name).symlink_to(tmp_path)
    assert path.is_symlink()
