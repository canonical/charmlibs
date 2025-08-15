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

"""Unit tests for methods of LocalPath."""

from __future__ import annotations

import grp
import os
import pwd
import stat
import typing

import pytest

import utils
from charmlibs.pathops import ContainerPath, LocalPath, _constants
from charmlibs.pathops._functions import _get_fileinfo

if typing.TYPE_CHECKING:
    import pathlib

    import ops

GOOD_PARENT_DIRECTORY_MODES = (
    '0o777',
    '0o766',
    '0o755',  # pebble default for mkdir
    '0o700',
)
# These 'bad' modes result in errors when used with ops.Container.make_dirs and creating parents.
# This occurs because Pebble applies the requested permissions to the parent directories.
# In this library, we follow the pathlib approach and do not apply the permissions to the parents.
#
# These permissions create the directories but raise an error due to lacking read permissions,
# because after a certain Pebble version some operation requiring read permissions is performed.
BAD_PARENT_DIRECTORY_MODES_CREATE = (
    '0o344',
    '0o333',
    '0o300',
)
# These permissions result in failure to create the subdirectories at all,
# because the first parent to be created is missing execute permissions,
# which are required to access its contents.
BAD_PARENT_DIRECTORY_MODES_NO_CREATE = (
    '0o666',
    '0o644',  # pebble default for file push
    '0o600',
    '0o544',
    '0o500',
    '0o444',
    '0o400',
    '0o200',
    '0o100',
    '0o010',
    '0o007',
    '0o000',
)
_MODES = (
    *GOOD_PARENT_DIRECTORY_MODES,
    *BAD_PARENT_DIRECTORY_MODES_NO_CREATE,
    *BAD_PARENT_DIRECTORY_MODES_CREATE,
)
ALL_MODES = tuple(sorted(_MODES, reverse=True))


@pytest.mark.parametrize(
    ('method', 'content'),
    [('write_bytes', b'hell\r\no\r'), ('write_text', 'hell\r\no\r'), ('mkdir', None)],
)
class TestChown:
    def test_unknown_user_raises_before_other_errors(
        self,
        container: ops.Container,
        tmp_path: pathlib.Path,
        method: str,
        content: bytes | str | None,
    ):
        args = [content] if content is not None else ()
        unknown_user = 'unknown_user'
        with pytest.raises(LookupError):
            pwd.getpwnam(unknown_user)
        parent = tmp_path / 'dirname'
        assert not parent.exists()
        path = parent / 'subdirname'
        assert not path.exists()
        container_path = ContainerPath(path, container=container)
        local_path = LocalPath(path)
        container_path_method = getattr(container_path, method)
        local_path_method = getattr(local_path, method)
        with pytest.raises(LookupError):
            container_path_method(*args, user=unknown_user)
        assert not path.exists()
        with pytest.raises(LookupError):
            local_path_method(*args, user=unknown_user)
        assert not path.exists()

    def test_unknown_group_raises_before_other_errors(
        self,
        container: ops.Container,
        tmp_path: pathlib.Path,
        method: str,
        content: bytes | str | None,
    ):
        args = [content] if content is not None else ()
        unknown_group = 'unknown_group'
        with pytest.raises(LookupError):
            grp.getgrnam(unknown_group)
        parent = tmp_path / 'dirname'
        assert not parent.exists()
        path = parent / 'subdirname'
        assert not path.exists()
        container_path = ContainerPath(path, container=container)
        local_path = LocalPath(path)
        container_path_method = getattr(container_path, method)
        local_path_method = getattr(local_path, method)
        with pytest.raises(LookupError):
            container_path_method(*args, group=unknown_group)
        assert not path.exists()
        with pytest.raises(LookupError):
            local_path_method(*args, group=unknown_group)
        assert not path.exists()


@pytest.mark.parametrize(('method', 'data'), [('write_bytes', b'bytes'), ('write_text', 'text')])
@pytest.mark.parametrize('mode_str', [None, *ALL_MODES])
@pytest.mark.parametrize(
    'exists_with_mode',
    (None, _constants.DEFAULT_WRITE_MODE, _constants.DEFAULT_WRITE_MODE | stat.S_IXOTH),
)
def test_write_methods_chmod(
    container: ops.Container,
    tmp_path: pathlib.Path,
    method: str,
    data: str | bytes,
    mode_str: str | None,
    exists_with_mode: int | None,
):
    mode = int(mode_str, base=8) if mode_str is not None else None
    path = tmp_path / 'path'
    # container
    container_path = ContainerPath(path, container=container)
    container_path_method = getattr(container_path, method)
    if exists_with_mode is not None:
        path.write_bytes(b'')
        path.chmod(exists_with_mode)
    else:
        assert not path.exists()
    container_path_method(data, mode=mode)
    assert path.exists()
    container_info = _get_fileinfo(container_path)
    # cleanup
    _unlink(path)
    # local
    local_path = LocalPath(path)
    local_path_method = getattr(local_path, method)
    if exists_with_mode is not None:
        path.write_bytes(b'')
        path.chmod(exists_with_mode)
    else:
        assert not path.exists()
    local_path_method(data, mode=mode)
    assert path.exists()
    local_info = _get_fileinfo(local_path)
    # cleanup
    _unlink(path)
    exclude = 'last_modified'
    container_dict = utils.info_to_dict(container_info, exclude=exclude)
    local_dict = utils.info_to_dict(local_info, exclude=exclude)
    assert local_dict == container_dict
    if mode is not None:
        assert local_dict['permissions'] == mode
    elif exists_with_mode is not None:
        assert local_dict['permissions'] == exists_with_mode
    else:
        assert local_dict['permissions'] == _constants.DEFAULT_WRITE_MODE


@pytest.mark.parametrize('mode_str', [*ALL_MODES, None])
class TestMkdirChmod:
    def test_ok(self, container: ops.Container, tmp_path: pathlib.Path, mode_str: str | None):
        mode = int(mode_str, base=8) if mode_str is not None else None
        path = tmp_path / 'directory'
        # container
        container_path = ContainerPath(path, container=container)
        assert not path.exists()
        if mode is not None:
            container_path.mkdir(mode=mode)
        else:
            container_path.mkdir()
        assert path.exists()
        assert path.is_dir()
        container_info = _get_fileinfo(container_path)
        # cleanup
        _rmdirs(path)
        # local
        local_path = LocalPath(path)
        assert not path.exists()
        if mode is not None:
            local_path.mkdir(mode=mode)
        else:
            local_path.mkdir()
        assert path.exists()
        assert path.is_dir()
        local_info = _get_fileinfo(local_path)
        # cleanup -- pytest is bad at cleaning up when permissions are funky
        _rmdirs(path)
        # comparison
        exclude = ('last_modified', 'permissions')
        container_dict = utils.info_to_dict(container_info, exclude=exclude)
        local_dict = utils.info_to_dict(local_info, exclude=exclude)
        assert local_dict == container_dict
        assert _oct(local_info.permissions) == _oct(container_info.permissions)

    def test_exists(self, container: ops.Container, tmp_path: pathlib.Path, mode_str: str | None):
        mode = int(mode_str, base=8) if mode_str is not None else None
        path = tmp_path / 'directory'
        path.mkdir()
        # container
        container_path = ContainerPath(path, container=container)
        if mode is not None:
            container_path.mkdir(exist_ok=True, mode=mode)
        else:
            container_path.mkdir(exist_ok=True)
        container_info = _get_fileinfo(container_path)
        # local
        container_path = LocalPath(path)
        if mode is not None:
            container_path.mkdir(exist_ok=True, mode=mode)
        else:
            container_path.mkdir(exist_ok=True)
        local_info = _get_fileinfo(container_path)
        # cleanup -- pytest is bad at cleaning up when permissions are funky
        _rmdirs(path)
        # comparison
        exclude = ('last_modified', 'permissions')
        container_dict = utils.info_to_dict(container_info, exclude=exclude)
        local_dict = utils.info_to_dict(local_info, exclude=exclude)
        assert local_dict == container_dict
        assert _oct(local_info.permissions) == _oct(container_info.permissions)

    @pytest.mark.parametrize('subdir_path', ['1/2', '1/2/3'])
    def test_parents(
        self,
        container: ops.Container,
        tmp_path: pathlib.Path,
        mode_str: str | None,
        subdir_path: str,
    ):
        mode = int(mode_str, base=8) if mode_str is not None else None
        path = tmp_path / subdir_path
        parents: list[pathlib.Path] = []
        for p in path.parents:
            if p == tmp_path:
                break
            parents.append(p)
        # container
        container_path = ContainerPath(path, container=container)
        assert not path.exists()
        assert not any(p.exists() for p in parents)
        if mode is not None:
            container_path.mkdir(parents=True, mode=mode)
        else:
            container_path.mkdir(parents=True)
        assert all(p.exists() for p in parents)
        assert all(p.is_dir() for p in parents)
        assert path.exists()
        assert path.is_dir()
        container_parent_info = _get_fileinfo(container_path.parent)
        container_info = _get_fileinfo(container_path)
        # cleanup
        _rmdirs(path, *parents)
        # local
        local_path = LocalPath(path)
        assert not path.exists()
        assert not any(p.exists() for p in parents)
        if mode is not None:
            local_path.mkdir(parents=True, mode=mode)
        else:
            local_path.mkdir(parents=True)
        assert all(p.exists() for p in parents)
        assert all(p.is_dir() for p in parents)
        assert path.exists()
        assert path.is_dir()
        local_parent_info = _get_fileinfo(local_path.parent)
        local_info = _get_fileinfo(local_path)
        # cleanup -- pytest is bad at cleaning up when permissions are funky
        _rmdirs(path, *parents)
        # comparison
        exclude = ('last_modified', 'permissions')
        container_dict = utils.info_to_dict(container_info, exclude=exclude)
        local_dict = utils.info_to_dict(local_info, exclude=exclude)
        assert local_dict == container_dict
        assert _oct(local_info.permissions) == _oct(container_info.permissions)
        container_parent_dict = utils.info_to_dict(container_parent_info, exclude=exclude)
        local_parent_dict = utils.info_to_dict(local_parent_info, exclude=exclude)
        assert local_parent_dict == container_parent_dict
        assert _oct(local_parent_info.permissions) == _oct(container_parent_info.permissions)


def _oct(i: int) -> str:
    return f'0o{i:03o}'


def _rmdirs(path: pathlib.Path, *paths: pathlib.Path):
    for p in (path, *paths):
        os.chmod(p, _constants.DEFAULT_MKDIR_MODE)
        p.rmdir()


def _unlink(path: pathlib.Path):
    os.chmod(path, _constants.DEFAULT_WRITE_MODE)
    path.unlink()
