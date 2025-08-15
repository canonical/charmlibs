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
import pathlib
import typing

import pytest

import utils
from charmlibs.pathops import ContainerPath, LocalPath, _constants, ensure_contents
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
    container: ops.Container, session_dir: pathlib.Path, filename: str, follow_symlinks: bool
):
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
        assert utils.info_to_dict(synthetic_result) == utils.info_to_dict(pebble_result)
