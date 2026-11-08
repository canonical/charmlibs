# Copyright 2024 Canonical Ltd.
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

"""Utilities for creating and working with :class:`ops.pebble.FileInfo` objects."""

from __future__ import annotations

import datetime
import grp
import pwd
import re
import stat
import typing

from ops import pebble

from . import _errors

if typing.TYPE_CHECKING:
    import pathlib

    from ._container_path import ContainerPath


_FT_MAP: dict[int, pebble.FileType] = {
    stat.S_IFREG: pebble.FileType.FILE,
    stat.S_IFDIR: pebble.FileType.DIRECTORY,
    stat.S_IFLNK: pebble.FileType.SYMLINK,
    stat.S_IFSOCK: pebble.FileType.SOCKET,
    stat.S_IFIFO: pebble.FileType.NAMED_PIPE,
    stat.S_IFBLK: pebble.FileType.DEVICE,  # block device
    stat.S_IFCHR: pebble.FileType.DEVICE,  # character device
}


def from_container_path(path: ContainerPath, follow_symlinks: bool = True) -> pebble.FileInfo:
    if follow_symlinks:
        return _get_fileinfo_directly(path)
    return _get_fileinfo_from_parent(path)


def _get_fileinfo_directly(path: ContainerPath) -> pebble.FileInfo:
    try:
        info_list = path._container.list_files(path._path, itself=True)
    except (pebble.APIError, pebble.PathError) as e:
        msg = repr(path)
        _errors.raise_if_matches_file_not_found(e, msg=msg)
        _errors.raise_if_matches_not_a_directory(e, msg=msg)
        _errors.raise_if_matches_permission(e, msg=msg)
        _errors.raise_if_matches_too_many_levels_of_symlinks(e, msg=msg)
        raise
    assert len(info_list) == 1, 'ops.Container.list_files with itself=True returns 1 item'
    return info_list[0]


def _get_fileinfo_from_parent(path: ContainerPath) -> pebble.FileInfo:
    try:
        info_list = path._container.list_files(
            path._path.parent, pattern=_escape_pattern(path.name)
        )
    except (pebble.APIError, pebble.PathError) as e:
        msg = repr(path)
        _errors.raise_if_matches_file_not_found(e, msg=msg)
        _errors.raise_if_matches_permission(e, msg=msg)
        raise
    if not info_list:
        _errors.raise_file_not_found(repr(path))
    assert len(info_list) == 1, 'ops.Container.list_files with non-* pattern should return 1 item'
    return info_list[0]


def _escape_pattern(name: str) -> str:
    """Return a pattern matching only this literal name, for Pebble (Go) and ops.testing (fnmatch).

    The two syntaxes differ, but both treat a single character in square brackets as a literal.
    """
    return re.sub(r'[*?\[\\]', lambda m: '[\\\\]' if m[0] == '\\' else f'[{m[0]}]', name)


def from_pathlib_path(path: pathlib.Path, follow_symlinks: bool = True) -> pebble.FileInfo:
    stat_result = path.stat() if follow_symlinks else path.lstat()
    utcoffset = datetime.datetime.now().astimezone().utcoffset()
    timezone = datetime.timezone(utcoffset) if utcoffset is not None else datetime.timezone.utc
    filetype = _FT_MAP.get(stat.S_IFMT(stat_result.st_mode), pebble.FileType.UNKNOWN)
    size = stat_result.st_size if filetype is pebble.FileType.FILE else None
    return pebble.FileInfo(
        path=str(path),
        name=path.name,
        type=filetype,
        size=size,
        permissions=stat.S_IMODE(stat_result.st_mode),
        last_modified=datetime.datetime.fromtimestamp(int(stat_result.st_mtime), tz=timezone),
        user_id=stat_result.st_uid,
        user=pwd.getpwuid(stat_result.st_uid).pw_name,
        group_id=stat_result.st_gid,
        group=grp.getgrgid(stat_result.st_gid).gr_name,
    )
