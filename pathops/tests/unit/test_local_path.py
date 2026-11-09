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
import pathlib
import pwd
import re
import shutil
from dataclasses import dataclass

import pytest

from charmlibs.pathops import LocalPath


class MockChown:
    calls: list[tuple[pathlib.Path, str | int | None, str | int | None]]

    def __init__(self):
        self.calls = []

    def __call__(
        self, path: pathlib.Path, user: str | int | None = None, group: str | int | None = None
    ) -> None:
        self.calls.append((path, user, group))
        return


@dataclass
class MockGetPwNam:
    pw_gid: int

    def __call__(self, _: str) -> MockPwdStruct:
        return MockPwdStruct(1)


@dataclass
class MockPwdStruct:
    pw_gid: int
    pw_uid: int = 0


@dataclass
class MockGrpStruct:
    gr_gid: int


def mock_pass(*args: object, **kwargs: object) -> None:
    pass


@pytest.fixture
def mock_chown():
    return MockChown()


@pytest.mark.parametrize(
    'method',
    ['write_bytes', 'write_text'],
)
@pytest.mark.parametrize(
    ('user', 'group', 'expected_ids'),
    (
        ('user-name', 'group-name', (7, 2)),
        ('user-name', None, (7, 1)),
        (None, 'group-name', (-1, 2)),
        (None, None, None),
    ),
)
def test_write_methods_chown_the_open_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    method: str,
    user: str | None,
    group: str | None,
    expected_ids: tuple[int, int] | None,
):
    calls: list[tuple[int, int]] = []

    def fchown(_fd: int, uid: int, gid: int) -> None:
        calls.append((uid, gid))

    def getpwnam(_name: str) -> MockPwdStruct:
        return MockPwdStruct(1, 7)

    def getgrnam(_name: str) -> MockGrpStruct:
        return MockGrpStruct(2)

    monkeypatch.setattr(os, 'fchown', fchown)
    monkeypatch.setattr(pwd, 'getpwnam', getpwnam)
    monkeypatch.setattr(grp, 'getgrnam', getgrnam)
    path = LocalPath(tmp_path, 'file')
    getattr(path, method)(b'data' if method == 'write_bytes' else 'data', user=user, group=group)
    assert path.read_bytes() == b'data'
    assert calls == ([expected_ids] if expected_ids else [])


@pytest.mark.parametrize('method', ['write_bytes', 'write_text'])
@pytest.mark.parametrize('mode', [0o600, 0o444])
@pytest.mark.parametrize('existing', [False, True])
def test_write_methods_set_mode_before_writing_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    method: str,
    mode: int,
    existing: bool,
):
    path = LocalPath(tmp_path, 'file')
    if existing:
        path.write_bytes(b'old content that is longer')
        path.chmod(0o644)
    modes_when_written: list[int] = []
    real_ftruncate = os.ftruncate

    def ftruncate(fd: int, length: int) -> None:
        # Truncation happens after the mode is set and before any new content is written.
        modes_when_written.append(os.fstat(fd).st_mode & 0o777)
        real_ftruncate(fd, length)

    monkeypatch.setattr(os, 'ftruncate', ftruncate)
    getattr(path, method)(b'new' if method == 'write_bytes' else 'new', mode=mode)
    assert modes_when_written == [mode]
    assert path.read_bytes() == b'new'
    assert path.stat().st_mode & 0o777 == mode


@pytest.mark.parametrize(
    ('method', 'content'),
    [('mkdir', None)],
)
@pytest.mark.parametrize(
    ('user', 'group'),
    (
        ('user-name', 'group-name'),
        ('user-name', None),
        (None, 'group-name'),
        (None, None),
    ),
)
def test_file_creation_methods_call_chown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    mock_chown: MockChown,
    method: str,
    content: bytes | str | None,
    user: str | None,
    group: str | None,
):
    stubbed_gid = 1
    monkeypatch.setattr(shutil, 'chown', mock_chown)
    monkeypatch.setattr(pwd, 'getpwnam', MockGetPwNam(stubbed_gid))
    monkeypatch.setattr(grp, 'getgrnam', mock_pass)
    args = [content] if content is not None else ()
    path = LocalPath(tmp_path, 'subdirectory')
    assert not path.exists()
    path_method = getattr(path, method)
    path_method(*args, user=user, group=group)
    assert path.exists()
    if method == 'write_bytes':
        assert isinstance(content, bytes)
        assert path.read_bytes() == content
    elif method == 'write_text':
        assert isinstance(content, str)
        expected_result = re.sub(r'\r\n|\r', '\n', content)
        assert path.read_text() == expected_result
    elif method == 'mkdir':
        assert path.is_dir()
    else:
        raise ValueError(f'Unexpected method: {method}')
    if (user, group) == (None, None):
        assert not mock_chown.calls
    else:
        (call,) = mock_chown.calls
        expected_group = group if group is not None else stubbed_gid
        assert call == (path, user, expected_group)


@pytest.mark.parametrize(
    ('data', 'newline', 'result'),
    [
        ('\n', None, '\n'),
        ('\n', '\n', '\n'),
        ('\n', '', '\n'),
        ('\n', '\r\n', '\r\n'),
        ('\n', '\r', '\r'),
        ('\r\n', None, '\r\n'),
        ('\r\n', '\n', '\r\n'),
        ('\r\n', '', '\r\n'),
        ('\r\n', '\r\n', '\r\r\n'),
        ('\r\n', '\r', '\r\r'),
    ],
)
def test_write_text_newline(tmp_path: pathlib.Path, data: str, newline: str | None, result: str):
    path = tmp_path / 'path'
    path.write_text(data, newline=newline)
    assert path.read_bytes() == result.encode()
    LocalPath(path).write_text(data, newline=newline)
    assert path.read_bytes() == result.encode()


def test_write_text_newline_value_error(tmp_path: pathlib.Path):
    path = tmp_path / 'path'
    with pytest.raises(ValueError):
        path.write_text('', newline='bad')
    with pytest.raises(ValueError):
        LocalPath(path).write_text('', newline='bad')


class TestGlobPattern:
    @pytest.fixture
    def populated_dir(self, tmp_path: pathlib.Path) -> pathlib.Path:
        (tmp_path / 'a.txt').write_text('')
        (tmp_path / 'b.txt').write_text('')
        (tmp_path / 'c.md').write_text('')
        return tmp_path

    def test_str_pattern(self, populated_dir: pathlib.Path):
        result = sorted(p.name for p in LocalPath(populated_dir).glob('*.txt'))
        assert result == ['a.txt', 'b.txt']

    def test_pathlib_pattern(self, populated_dir: pathlib.Path):
        pattern = pathlib.PurePosixPath('*.txt')
        result = sorted(p.name for p in LocalPath(populated_dir).glob(pattern))
        assert result == ['a.txt', 'b.txt']

    def test_custom_pathlike_pattern(self, populated_dir: pathlib.Path):
        class _Pattern:
            def __fspath__(self) -> str:
                return '*.md'

        result = sorted(p.name for p in LocalPath(populated_dir).glob(_Pattern()))
        assert result == ['c.md']
