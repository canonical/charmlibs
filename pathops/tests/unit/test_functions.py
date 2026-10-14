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
import stat
import typing

import ops
import pytest
from ops import pebble

import utils
from charmlibs.pathops import ContainerPath, LocalPath, _constants, ensure_text_transform
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


@pytest.mark.parametrize('path_type', [str, pathlib.Path, LocalPath])
@pytest.mark.parametrize(
    ('initial', 'result', 'expected_arg', 'expected_bytes', 'changed'),
    (
        (None, 'hello\n', None, b'hello\n', True),
        (None, '', None, b'', True),
        (b'', '', '', b'', False),
        (b'', 'x', '', b'x', True),
        ('héllo\n'.encode(), 'héllo\n', 'héllo\n', 'héllo\n'.encode(), False),
        (b'hello', '', 'hello', b'', True),
        # newlines are translated to '\n' for transform, and the file ends up with the result
        (b'a\r\nb\rc\n', 'a\nb\nc\n', 'a\nb\nc\n', b'a\nb\nc\n', True),
        (b'a\r\nb\rc\n', 'a\nb\nc\nd\n', 'a\nb\nc\n', b'a\nb\nc\nd\n', True),
        # returned text is written as is
        (None, 'a\r\nb\r', None, b'a\r\nb\r', True),
    ),
)
def test_ensure_text_transform(
    tmp_path: pathlib.Path,
    path_type: type[str] | type[pathlib.Path],
    initial: bytes | None,
    result: str,
    expected_arg: str | None,
    expected_bytes: bytes,
    changed: bool,
):
    path = tmp_path / 'parent' / 'path'
    if initial is not None:
        path.parent.mkdir()
        path.write_bytes(initial)
        path.chmod(_constants.DEFAULT_WRITE_MODE)
    calls: list[str | None] = []

    def transform(existing: str | None) -> str:
        calls.append(existing)
        return result

    assert ensure_text_transform(path_type(path), transform) == changed
    assert calls == [expected_arg]
    assert path.read_bytes() == expected_bytes
    assert stat.S_IMODE(path.stat().st_mode) == _constants.DEFAULT_WRITE_MODE


def _identity(text: str | None) -> str:
    assert text is not None
    return text


def test_ensure_text_transform_enforces_mode_when_contents_unchanged(tmp_path: pathlib.Path):
    path = tmp_path / 'path'
    path.write_bytes(b'x\n')
    path.chmod(0o600)
    assert ensure_text_transform(path, _identity, mode=0o640)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert path.read_bytes() == b'x\n'
    assert not ensure_text_transform(path, _identity, mode=0o640)


def test_ensure_text_transform_normalises_newlines_once(tmp_path: pathlib.Path):
    path = tmp_path / 'path'
    path.write_bytes(b'a\r\nb\r')
    path.chmod(_constants.DEFAULT_WRITE_MODE)
    assert ensure_text_transform(path, _identity)
    assert path.read_bytes() == b'a\nb\n'
    assert not ensure_text_transform(path, _identity)


@pytest.mark.parametrize('bad', [None, b'x'])
@pytest.mark.parametrize('exists', [True, False])
def test_ensure_text_transform_rejects_wrong_return_type(
    tmp_path: pathlib.Path, bad: object, exists: bool
):
    path = tmp_path / 'path'
    if exists:
        path.write_bytes(b'x')
        path.chmod(0o600)
    with pytest.raises(TypeError):
        ensure_text_transform(path, lambda _: bad, mode=0o644)  # type: ignore
    if exists:
        assert path.read_bytes() == b'x'
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        assert not path.exists()


class _TransformError(Exception):
    pass


def _raise(_: object) -> typing.NoReturn:
    raise _TransformError()


@pytest.mark.parametrize('exists', [True, False])
def test_ensure_text_transform_propagates_transform_errors_without_changes(
    tmp_path: pathlib.Path, exists: bool
):
    path = tmp_path / 'parent' / 'path'
    if exists:
        path.parent.mkdir()
        path.write_bytes(b'x')
        path.chmod(0o600)
    with pytest.raises(_TransformError):
        ensure_text_transform(path, _raise, mode=0o644)
    if exists:
        assert path.read_bytes() == b'x'
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        assert not path.parent.exists()


def test_ensure_text_transform_propagates_decode_errors_without_changes(tmp_path: pathlib.Path):
    path = tmp_path / 'path'
    path.write_bytes(b'\xff')
    path.chmod(0o600)
    calls: list[str | None] = []

    def transform(existing: str | None) -> str:
        calls.append(existing)
        return ''

    with pytest.raises(UnicodeDecodeError):
        ensure_text_transform(path, transform, mode=0o644)
    assert not calls
    assert path.read_bytes() == b'\xff'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
