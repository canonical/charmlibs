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

"""Public helper functions exported by this package."""

from __future__ import annotations

import pathlib
import shutil
import typing

import ops

from . import _constants, _errors, _fileinfo
from ._container_path import ContainerPath
from ._local_path import LocalPath

if typing.TYPE_CHECKING:
    import os
    from typing import BinaryIO, TextIO

    from typing_extensions import TypeIs

    from ._types import PathProtocol


def ensure_contents(
    path: str | os.PathLike[str] | PathProtocol,
    source: bytes | str | BinaryIO | TextIO,
    *,
    mode: int = _constants.DEFAULT_WRITE_MODE,
    user: str | None = None,
    group: str | None = None,
) -> bool:
    """Ensure ``source`` can be read from ``path``. Return True if any changes were made.

    Ensure that ``path`` exists, contains ``source``, has the correct permissions (``mode``),
    and has the correct file ownership (``user`` and ``group``).

    Args:
        path: A local or remote filesystem path.
        source: The desired contents in ``str`` or ``bytes`` form, or an object with a ``.read()``
            method which returns a ``str`` or ``bytes`` object.
        mode: The desired file permissions.
        user: The desired file owner, or ``None`` to not change the owner.
        group: The desired group, or ``None`` to not change the group.

    Returns:
        ``True`` if any changes were made, including permissions or ownership, otherwise ``False``.

    Raises:
        LookupError: if the user or group is unknown.
        NotADirectoryError: if the parent exists as a non-directory file.
        PermissionError: if the user does not have permissions for the operation.
        :class:`PebbleConnectionError`: if the remote Pebble client cannot be reached.
    """
    if _is_str_pathlike(path):
        path = LocalPath(path)
    source = _as_bytes(source)
    try:
        info = _get_fileinfo(path)
    except FileNotFoundError:
        pass  # file doesn't exist, so writing is required
    else:  # check if metadata and contents already match
        if (
            (info.permissions == mode)
            and (user is None or info.user == user)
            and (group is None or info.group == group)
            and (path.read_bytes() == source)
        ):
            return False  # everything matches, so writing is not required
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source, mode=mode, user=user, group=group)
    return True


def rmtree(path: str | os.PathLike[str] | PathProtocol) -> None:
    """Remove the directory tree rooted at ``path``.

    Strings or ``os.PathLike`` objects are treated as local paths, and are removed with
    :func:`shutil.rmtree`. Otherwise ``path`` must be a :class:`ContainerPath`, which is removed
    with Pebble's recursive remove.

    ``path`` itself must be a directory, not a symlink to one. Symlinks inside the tree are
    removed, not followed.

    Args:
        path: A local or remote filesystem path to a directory.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        NotADirectoryError: if ``path`` is not a directory or is a symlink.
        PermissionError: if the user does not have permissions for the operation.
        TypeError: if ``path`` is not a ``str``, :class:`os.PathLike`, or :class:`ContainerPath`.
        :class:`PebbleConnectionError`: if the remote Pebble client cannot be reached.
    """
    if _is_str_pathlike(path):
        _rmtree_local(pathlib.Path(path))
    elif isinstance(path, ContainerPath):
        _rmtree_container(path)
    else:
        raise TypeError(f'Expected str, os.PathLike, or ContainerPath, got {type(path).__name__}')


def _rmtree_local(path: pathlib.Path) -> None:
    # shutil.rmtree raises a bare OSError for symlinks, but handles other cases as we'd like.
    if path.is_symlink():
        _errors.raise_not_a_directory(str(path))
    shutil.rmtree(path)


def _rmtree_container(path: ContainerPath) -> None:
    # Pebble's recursive remove succeeds silently for missing paths, and removes files and
    # symlinks, so check the path is a real directory first.
    info = _fileinfo.from_container_path(path, follow_symlinks=False)
    if info.type != ops.pebble.FileType.DIRECTORY:
        _errors.raise_not_a_directory(repr(path))
    try:
        path._container.remove_path(path._path, recursive=True)
    except ops.pebble.PathError as e:
        _errors.raise_if_matches_permission(e, msg=repr(path))
        raise


def _is_str_pathlike(obj: object) -> TypeIs[str | os.PathLike[str]]:
    return isinstance(obj, str) or hasattr(obj, '__fspath__')


def _get_fileinfo(
    path: str | os.PathLike[str] | PathProtocol, follow_symlinks: bool = True
) -> ops.pebble.FileInfo:
    if isinstance(path, ContainerPath):
        return _fileinfo.from_container_path(path, follow_symlinks=follow_symlinks)
    assert _is_str_pathlike(path)
    return _fileinfo.from_pathlib_path(pathlib.Path(path), follow_symlinks=follow_symlinks)


def _as_bytes(source: bytes | str | BinaryIO | TextIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        return source.encode()
    return _as_bytes(source.read())
