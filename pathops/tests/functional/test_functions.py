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

"""Tests that use a real Pebble to test helper functions."""

from __future__ import annotations

import io
import os
import pathlib
import typing

import pytest

import utils
from charmlibs.pathops import ContainerPath, LocalPath, _constants, ensure_contents, rmtree
from charmlibs.pathops._functions import _get_fileinfo

if typing.TYPE_CHECKING:
    from typing import Literal

    import ops


@pytest.mark.parametrize('exists', [True, False])
@pytest.mark.parametrize('mode', [_constants.DEFAULT_WRITE_MODE, 0o600])
@pytest.mark.parametrize('input_type', ['bytes', 'str', 'bytes_io', 'str_io'])
@pytest.mark.parametrize('path_type', [str, pathlib.Path, LocalPath, ContainerPath])
@pytest.mark.parametrize('contents', [b'hel\rl\r\no\n'])
def test_ensure_contents(
    tmp_path: pathlib.Path,
    container: ops.Container,
    path_type: type[str] | type[pathlib.Path] | type[ContainerPath],
    contents: bytes,
    input_type: Literal['bytes', 'str', 'bytes_io', 'str_io'],
    mode: int,
    exists: bool,
):
    parent = tmp_path / 'parent'
    path = parent / 'path'
    if exists:
        parent.mkdir()
        path.write_bytes(contents)
        path.chmod(_constants.DEFAULT_WRITE_MODE)
    # target
    if issubclass(path_type, ContainerPath):
        target = ContainerPath(path, container=container)
    else:
        target = path_type(path)
    # source
    if input_type == 'bytes':
        source = contents
    elif input_type == 'str':
        source = contents.decode()
    elif input_type == 'bytes_io':
        source = io.BytesIO(contents)
    elif input_type == 'str_io':
        source = io.StringIO(contents.decode())
    else:
        raise ValueError(f'Unknown input type: {input_type!r}')
    # ensure_contents
    write_required = ensure_contents(path=target, source=source, mode=mode)
    # asserts
    if exists and mode == _constants.DEFAULT_WRITE_MODE:
        assert not write_required
    else:
        assert write_required
    assert path.read_bytes() == contents
    info = _get_fileinfo(path)
    assert info.permissions == mode


@pytest.mark.parametrize('follow_symlinks', [True, False])
@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
def test_get_fileinfo(
    container: ops.Container,
    session_dir: pathlib.Path,
    pebble_resolves_groups: bool,
    filename: str,
    follow_symlinks: bool,
):
    exclude: list[str] = []
    if not pebble_resolves_groups:
        exclude.append('group')
    path = session_dir / filename
    try:
        pebble_result = _get_fileinfo(
            ContainerPath(path, container=container), follow_symlinks=follow_symlinks
        )
    except OSError as e:
        with pytest.raises(type(e)):
            _get_fileinfo(path, follow_symlinks=follow_symlinks)
    else:
        synthetic_result = _get_fileinfo(path, follow_symlinks=follow_symlinks)
        synthetic_dict = utils.info_to_dict(synthetic_result, exclude=exclude)
        pebble_dict = utils.info_to_dict(pebble_result, exclude=exclude)
        assert synthetic_dict == pebble_dict


PathType = type[str] | type[pathlib.Path] | type[ContainerPath]
PATH_TYPES: tuple[PathType, ...] = (str, pathlib.Path, LocalPath, ContainerPath)


def as_path(
    path: pathlib.Path, path_type: PathType, container: ops.Container
) -> str | pathlib.Path | ContainerPath:
    if issubclass(path_type, ContainerPath):
        return ContainerPath(path, container=container)
    return path_type(path)


@pytest.mark.parametrize('path_type', PATH_TYPES)
def test_rmtree_removes_tree(
    tmp_path: pathlib.Path, container: ops.Container, path_type: PathType
):
    root = tmp_path / 'target'
    (root / 'sub').mkdir(parents=True)
    (root / 'file.txt').write_bytes(b'data')
    (root / 'sub' / 'nested.txt').write_bytes(b'data')
    (root / 'sub' / 'empty').mkdir()
    rmtree(as_path(root, path_type, container))
    assert not os.path.lexists(root)


@pytest.mark.parametrize('path_type', PATH_TYPES)
def test_rmtree_not_found(tmp_path: pathlib.Path, container: ops.Container, path_type: PathType):
    with pytest.raises(FileNotFoundError):
        rmtree(as_path(tmp_path / 'does_not_exist', path_type, container))


@pytest.mark.parametrize('path_type', PATH_TYPES)
def test_rmtree_regular_file(
    tmp_path: pathlib.Path, container: ops.Container, path_type: PathType
):
    file = tmp_path / 'file.txt'
    file.write_bytes(b'data')
    with pytest.raises(NotADirectoryError):
        rmtree(as_path(file, path_type, container))
    assert file.read_bytes() == b'data'


@pytest.mark.parametrize('target', ['real_dir', 'does_not_exist'])
@pytest.mark.parametrize('path_type', PATH_TYPES)
def test_rmtree_symlink(
    tmp_path: pathlib.Path,
    container: ops.Container,
    path_type: PathType,
    target: str,
):
    (tmp_path / 'real_dir').mkdir()
    (tmp_path / 'real_dir' / 'file.txt').write_bytes(b'data')
    link = tmp_path / 'link'
    link.symlink_to(tmp_path / target)
    with pytest.raises(NotADirectoryError):
        rmtree(as_path(link, path_type, container))
    assert os.path.lexists(link)
    assert (tmp_path / 'real_dir' / 'file.txt').read_bytes() == b'data'


@pytest.mark.parametrize('target', ['outside', 'outside/precious.txt', 'does_not_exist'])
@pytest.mark.parametrize('path_type', PATH_TYPES)
def test_rmtree_removes_symlinks_in_tree_without_following(
    tmp_path: pathlib.Path,
    container: ops.Container,
    path_type: PathType,
    target: str,
):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'precious.txt').write_bytes(b'keep me')
    root = tmp_path / 'target'
    (root / 'sub').mkdir(parents=True)
    (root / 'sub' / 'link').symlink_to(tmp_path / target)
    rmtree(as_path(root, path_type, container))
    assert not os.path.lexists(root)
    assert [p.name for p in outside.iterdir()] == ['precious.txt']
    assert (outside / 'precious.txt').read_bytes() == b'keep me'
