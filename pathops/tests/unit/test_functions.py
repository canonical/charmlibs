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

"""Tests that don't use a real Pebble to test helper functions."""

from __future__ import annotations

import pathlib
import typing

import ops
import pytest
from ops import pebble

import utils
from charmlibs.pathops import ContainerPath, rmtree
from charmlibs.pathops._functions import _get_fileinfo

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


@pytest.mark.parametrize(
    ('mock', 'error'),
    (
        (utils.raise_connection_error, pebble.ConnectionError),
        (utils.raise_unknown_api_error, pebble.APIError),
    ),
)
def test_get_fileinfo_reraises_unhandled_pebble_errors(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
    mock: Callable[[Any], None],
    error: type[Exception],
):
    monkeypatch.setattr(container, 'list_files', mock)
    with pytest.raises(error):
        _get_fileinfo(ContainerPath('/', container=container))


def _fileinfo(path: str, file_type: pebble.FileType) -> pebble.FileInfo:
    return pebble.FileInfo(
        path=path,
        name=path.split('/')[-1],
        type=file_type,
        size=None,
        permissions=0o755,
        last_modified=None,  # type: ignore[arg-type]
        user_id=None,
        user=None,
        group_id=None,
        group=None,
    )


def _list_files_returning(
    path: str, file_type: pebble.FileType
) -> Callable[..., list[pebble.FileInfo]]:
    def list_files(*args: object, **kwargs: object) -> list[pebble.FileInfo]:
        return [_fileinfo(path, file_type)]

    return list_files


_list_files_mydir = _list_files_returning('/mydir', pebble.FileType.DIRECTORY)


def test_rmtree_container_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
):
    monkeypatch.setattr(container, 'list_files', utils.raise_not_found)
    with pytest.raises(FileNotFoundError):
        rmtree(ContainerPath('/mydir', container=container))


@pytest.mark.parametrize('file_type', (pebble.FileType.FILE, pebble.FileType.SYMLINK))
def test_rmtree_container_not_a_directory(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
    file_type: pebble.FileType,
):
    monkeypatch.setattr(container, 'list_files', _list_files_returning('/path', file_type))
    with pytest.raises(NotADirectoryError):
        rmtree(ContainerPath('/path', container=container))


def test_rmtree_container_permission_error(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
):
    monkeypatch.setattr(container, 'list_files', _list_files_mydir)
    monkeypatch.setattr(container, 'remove_path', utils.raise_permission_denied)
    with pytest.raises(PermissionError):
        rmtree(ContainerPath('/mydir', container=container))


def test_rmtree_container_unknown_path_error_reraised(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
):
    monkeypatch.setattr(container, 'list_files', _list_files_mydir)
    monkeypatch.setattr(container, 'remove_path', utils.raise_unknown_path_error)
    with pytest.raises(pebble.PathError):
        rmtree(ContainerPath('/mydir', container=container))


def test_rmtree_container_connection_error_from_list_files(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
):
    monkeypatch.setattr(container, 'list_files', utils.raise_connection_error)
    with pytest.raises(pebble.ConnectionError):
        rmtree(ContainerPath('/mydir', container=container))


def test_rmtree_container_connection_error_from_remove_path(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
):
    monkeypatch.setattr(container, 'list_files', _list_files_mydir)
    monkeypatch.setattr(container, 'remove_path', utils.raise_connection_error)
    with pytest.raises(pebble.ConnectionError):
        rmtree(ContainerPath('/mydir', container=container))


def test_rmtree_container_success(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
):
    removed: list[tuple[object, ...]] = []

    def _record_remove_path(path: object, recursive: bool = False) -> None:
        removed.append((path, recursive))

    monkeypatch.setattr(container, 'list_files', _list_files_mydir)
    monkeypatch.setattr(container, 'remove_path', _record_remove_path)
    rmtree(ContainerPath('/mydir', container=container))
    assert removed == [(pathlib.PurePosixPath('/mydir'), True)]


def test_rmtree_unsupported_type():
    with pytest.raises(TypeError):
        rmtree(object())  # type: ignore[arg-type]
