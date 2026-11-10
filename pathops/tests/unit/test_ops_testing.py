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

import os
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


def test_missing_child_of_symlink_to_directory(container: ops.Container, tmp_path: pathlib.Path):
    (tmp_path / 'dir').mkdir()
    (tmp_path / 'link').symlink_to(tmp_path / 'dir')
    path = ContainerPath(MOUNT, 'link/missing', container=container)
    path.unlink(missing_ok=True)
    assert not path.is_symlink()
    with pytest.raises(FileNotFoundError):
        path.unlink()
    with pytest.raises(FileNotFoundError):
        path.rmdir()


def test_missing_child_of_directory(container: ops.Container, tmp_path: pathlib.Path):
    (tmp_path / 'dir').mkdir()
    path = ContainerPath(MOUNT, 'dir/missing', container=container)
    path.unlink(missing_ok=True)
    with pytest.raises(FileNotFoundError):
        path.rmdir()


@pytest.mark.parametrize('missing_ok', (False, True))
def test_unlink_file_parent(container: ops.Container, tmp_path: pathlib.Path, missing_ok: bool):
    (tmp_path / 'file').touch()
    path = ContainerPath(MOUNT, 'file/child', container=container)
    with pytest.raises(NotADirectoryError):
        path.unlink(missing_ok=missing_ok)


@pytest.mark.parametrize('missing_ok', (False, True))
def test_unlink_file_parent_with_same_name(
    container: ops.Container, tmp_path: pathlib.Path, missing_ok: bool
):
    (tmp_path / 'file').touch()
    path = ContainerPath(MOUNT, 'file/file', container=container)
    with pytest.raises(NotADirectoryError):
        path.unlink(missing_ok=missing_ok)
    assert (tmp_path / 'file').exists()


def test_unlink_child_with_same_name_as_directory_parent(
    container: ops.Container, tmp_path: pathlib.Path
):
    (tmp_path / 'name').mkdir()
    (tmp_path / 'name' / 'name').touch()
    ContainerPath(MOUNT, 'name/name', container=container).unlink()
    assert not (tmp_path / 'name' / 'name').exists()
    assert (tmp_path / 'name').exists()


@pytest.fixture
def non_directory_links(tmp_path: pathlib.Path) -> tuple[str, ...]:
    (tmp_path / 'file').touch()
    os.mkfifo(tmp_path / 'fifo')
    links = {'to_file': 'file', 'to_fifo': 'fifo', 'to_to_file': 'to_file'}
    for name, target in links.items():
        (tmp_path / name).symlink_to(target)
    return tuple(links)


@pytest.mark.parametrize('missing_ok', (False, True))
@pytest.mark.parametrize('same_name', (False, True))
def test_unlink_symlink_to_non_directory_parent(
    container: ops.Container,
    non_directory_links: tuple[str, ...],
    same_name: bool,
    missing_ok: bool,
):
    for link in non_directory_links:
        path = ContainerPath(MOUNT, link, link if same_name else 'child', container=container)
        with pytest.raises(NotADirectoryError):
            path.unlink(missing_ok=missing_ok)


@pytest.mark.parametrize('same_name', (False, True))
def test_rmdir_symlink_to_non_directory_parent(
    container: ops.Container, non_directory_links: tuple[str, ...], same_name: bool
):
    for link in non_directory_links:
        path = ContainerPath(MOUNT, link, link if same_name else 'child', container=container)
        with pytest.raises(NotADirectoryError):
            path.rmdir()


def test_exists_file_parent(container: ops.Container, tmp_path: pathlib.Path):
    (tmp_path / 'file').touch()
    assert not ContainerPath(MOUNT, 'file/child', container=container).exists()


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
