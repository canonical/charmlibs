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

"""Tests that use a real Pebble to test ContainerPath."""

from __future__ import annotations

import errno
import getpass
import grp
import pathlib
import pwd
import sys
import typing

import pytest

import utils
from charmlibs.pathops import ContainerPath, LocalPath

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    import ops


@pytest.mark.parametrize(
    ('file', 'error'),
    (
        (utils.EMPTY_DIR_NAME, IsADirectoryError),
        (utils.BROKEN_SYMLINK_NAME, FileNotFoundError),
        (utils.MISSING_FILE_NAME, FileNotFoundError),
        (utils.SOCKET_NAME, OSError),  # ContainerPath will raise FileNotFoundError
    ),
)
@pytest.mark.parametrize('method', ('read_bytes', 'read_text'))
def test_read_method_filetype_errors(
    container: ops.Container,
    session_dir: pathlib.Path,
    method: str,
    file: str,
    error: type[Exception],
):
    pathlib_method = getattr(pathlib.Path, method)
    with pytest.raises(error):
        pathlib_method(session_dir / file)
    containerpath_method = getattr(ContainerPath, method)
    container_path = ContainerPath(session_dir, file, container=container)
    with pytest.raises(error):
        containerpath_method(container_path)


class TestReadText:
    @pytest.mark.parametrize('newline', (None, ''))
    @pytest.mark.parametrize('filename', utils.TEXT_FILES)
    def test_ok(
        self,
        container: ops.Container,
        session_dir: pathlib.Path,
        filename: str,
        newline: str | None,
    ):
        path = session_dir / filename
        container_path = ContainerPath(path, container=container)
        try:  # python 3.13+ only
            kwargs: dict[str, Any] = {'newline': newline}
            pathlib_result = path.read_text(**kwargs)
        except TypeError:
            pathlib_result = path.read_text()
            container_result = container_path.read_text()
        else:
            container_result = container_path.read_text(newline=newline)
        assert container_result == pathlib_result

    @pytest.mark.parametrize('filename', [next(iter(utils.UTF16_BINARY_FILES))])
    def test_unicode_errors(
        self,
        container: ops.Container,
        session_dir: pathlib.Path,
        filename: str,
    ):
        path = session_dir / filename
        with pytest.raises(UnicodeError):
            path.read_text()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(UnicodeError):
            container_path.read_text()

    @pytest.mark.parametrize(('filename', 'contents'), tuple(utils.TEXT_FILES.items()))
    def test_newline_arg(
        self,
        container: ops.Container,
        tmp_path: pathlib.Path,
        filename: str,
        contents: str,
    ):
        path = tmp_path / filename
        container_path = ContainerPath(path, container=container)
        path.write_text(contents)
        if path.read_text() != contents:
            assert container_path.read_text() != contents
        assert container_path.read_text(newline='') == contents


@pytest.mark.parametrize('filename', [*utils.TEXT_FILES, *utils.BINARY_FILES])
def test_read_bytes(container: ops.Container, session_dir: pathlib.Path, filename: str):
    path = session_dir / filename
    pathlib_result = path.read_bytes()
    container_result = ContainerPath(path, container=container).read_bytes()
    assert container_result == pathlib_result


class TestIterDir:
    def test_ok(self, container: ops.Container, session_dir: pathlib.Path):
        pathlib_list = list(session_dir.iterdir())
        pathlib_set = {str(p) for p in pathlib_list}
        assert len(pathlib_list) == len(pathlib_set)
        container_path = ContainerPath(session_dir, container=container)
        container_list = list(container_path.iterdir())
        container_set = {str(p) for p in container_list}
        assert len(container_list) == len(container_set)
        assert container_set == pathlib_set

    @pytest.mark.parametrize(
        ('file', 'error'),
        (
            (utils.BINARY_FILE_NAME, NotADirectoryError),
            (utils.TEXT_FILE_NAME, NotADirectoryError),
            (utils.BROKEN_SYMLINK_NAME, FileNotFoundError),
            (utils.MISSING_FILE_NAME, FileNotFoundError),
            (utils.SOCKET_NAME, NotADirectoryError),  # ContainerPath raises NotADirectory
        ),
    )
    def test_filetype_errors(
        self,
        container: ops.Container,
        session_dir: pathlib.Path,
        file: str,
        error: type[Exception],
    ):
        path = session_dir / file
        with pytest.raises(error):
            next(path.iterdir())
        container_path = ContainerPath(path, container=container)
        with pytest.raises(error):
            next(container_path.iterdir())


class TestGlob:
    @pytest.mark.parametrize(
        'pattern',
        (
            '*',
            '*.txt',
            'foo*',
            'ba*.txt',
            f'{utils.NESTED_DIR_NAME}/*.txt',
            f'{utils.NESTED_DIR_NAME}*/*.txt',
            f'*{utils.NESTED_DIR_NAME}/*.txt',
            f'{utils.NESTED_DIR_PATTERN}/*.txt',
            '*/*.txt',
        ),
    )
    def test_ok(self, container: ops.Container, session_dir: pathlib.Path, pattern: str):
        pathlib_result = sorted(str(p) for p in session_dir.glob(pattern))
        container_path = ContainerPath(session_dir, container=container)
        container_result = sorted(str(p) for p in container_path.glob(pattern))
        assert container_result == pathlib_result

    def test_pattern_is_case_sensitive(self, container: ops.Container, session_dir: pathlib.Path):
        pattern = f'*/{utils.TEXT_FILE_NAME}'
        container_path = ContainerPath(session_dir, container=container)
        pathlib_result = sorted(str(p) for p in session_dir.glob(pattern))
        container_result = sorted(str(p) for p in container_path.glob(pattern))
        assert pathlib_result
        assert container_result
        assert container_result == pathlib_result
        pattern = pattern.upper()
        assert not (session_dir / utils.NESTED_DIR_NAME / pattern).exists()
        pathlib_result = sorted(str(p) for p in session_dir.glob(pattern))
        container_result = sorted(str(p) for p in container_path.glob(pattern))
        assert not pathlib_result
        assert not container_result
        assert container_result == pathlib_result

    @pytest.mark.parametrize('pattern', ['*', '*.txt'])
    def test_non_directory_target(
        self, container: ops.Container, session_dir: pathlib.Path, pattern: str
    ):
        path = session_dir / utils.TEXT_FILE_NAME
        pathlib_result = list(path.glob(pattern))
        container_path = ContainerPath(path, container=container)
        container_result = list(container_path.glob(pattern))
        assert container_result == pathlib_result

    @pytest.mark.parametrize('pattern', ['/'])
    def test_not_implemented(
        self, container: ops.Container, session_dir: pathlib.Path, pattern: str
    ):
        with pytest.raises(NotImplementedError):
            list(session_dir.glob(pattern))
        container_path = ContainerPath(session_dir, container=container)
        with pytest.raises(NotImplementedError):
            list(container_path.glob(pattern))

    @pytest.mark.parametrize('pattern', [f'{utils.NESTED_DIR_NAME}/**/*.txt', '**/*.txt'])
    def test_rglob_not_implemented_in_container_path(
        self, container: ops.Container, session_dir: pathlib.Path, pattern: str
    ):
        list(session_dir.glob(pattern))  # pattern is fine
        container_path = ContainerPath(session_dir, container=container)
        with pytest.raises(NotImplementedError):
            list(container_path.glob(pattern))

    @pytest.mark.parametrize('pattern', ['**.txt', '***/*.txt'])
    def test_bad_asterix_pattern(
        self, container: ops.Container, session_dir: pathlib.Path, pattern: str
    ):
        try:
            list(session_dir.glob(pattern))
        except ValueError:
            assert sys.version_info < (3, 13)
        else:
            assert sys.version_info >= (3, 13)
        container_path = ContainerPath(session_dir, container=container)
        with pytest.raises(ValueError):
            list(container_path.glob(pattern))

    def test_bad_dot_pattern(self, container: ops.Container, session_dir: pathlib.Path):
        pattern = '.'
        try:
            list(session_dir.glob(pattern))
        except IndexError:
            assert sys.version_info < (3, 13)
        except ValueError:
            assert sys.version_info >= (3, 13)
        container_path = ContainerPath(session_dir, container=container)
        with pytest.raises(ValueError):
            list(container_path.glob(pattern))

    def test_bad_empty_pattern(self, container: ops.Container, session_dir: pathlib.Path):
        pattern = ''
        with pytest.raises(ValueError):
            list(session_dir.glob(pattern))
        container_path = ContainerPath(session_dir, container=container)
        with pytest.raises(ValueError):
            list(container_path.glob(pattern))


@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
@pytest.mark.parametrize('method', ['owner', 'group'])
def test_owner_and_group(
    container: ops.Container, session_dir: pathlib.Path, method: str, filename: str
):
    path = session_dir / filename
    pathlib_method = getattr(path, method)
    container_path = ContainerPath(path, container=container)
    container_method = getattr(container_path, method)
    try:
        pathlib_result = pathlib_method()
    except Exception as e:
        with pytest.raises(type(e)):
            container_result = container_method()
    else:
        container_result = container_method()
        assert container_result == pathlib_result


@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
def test_exists(container: ops.Container, session_dir: pathlib.Path, filename: str):
    pathlib_path = session_dir / filename
    container_path = ContainerPath(session_dir, filename, container=container)
    pathlib_result = pathlib_path.exists()
    container_result = container_path.exists()
    assert container_result == pathlib_result


@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
def test_is_dir(container: ops.Container, session_dir: pathlib.Path, filename: str):
    pathlib_path = session_dir / filename
    container_path = ContainerPath(session_dir, filename, container=container)
    pathlib_result = pathlib_path.is_dir()
    container_result = container_path.is_dir()
    assert container_result == pathlib_result


@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
def test_is_file(container: ops.Container, session_dir: pathlib.Path, filename: str):
    pathlib_path = session_dir / filename
    container_path = ContainerPath(session_dir, filename, container=container)
    pathlib_result = pathlib_path.is_file()
    container_result = container_path.is_file()
    assert container_result == pathlib_result


@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
def test_is_fifo(container: ops.Container, session_dir: pathlib.Path, filename: str):
    pathlib_path = session_dir / filename
    container_path = ContainerPath(session_dir, filename, container=container)
    pathlib_result = pathlib_path.is_fifo()
    container_result = container_path.is_fifo()
    assert container_result == pathlib_result


@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
def test_is_socket(container: ops.Container, session_dir: pathlib.Path, filename: str):
    pathlib_path = session_dir / filename
    container_path = ContainerPath(session_dir, filename, container=container)
    pathlib_result = pathlib_path.is_socket()
    container_result = container_path.is_socket()
    assert container_result == pathlib_result


@pytest.mark.parametrize('filename', utils.FILENAMES_PLUS)
def test_is_symlink(container: ops.Container, session_dir: pathlib.Path, filename: str):
    pathlib_path = session_dir / filename
    container_path = ContainerPath(session_dir, filename, container=container)
    pathlib_result = pathlib_path.is_symlink()
    container_result = container_path.is_symlink()
    assert container_result == pathlib_result


class TestRmDir:
    def test_ok(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'directory'
        path.mkdir()
        container_path = ContainerPath(path, container=container)
        container_path.rmdir()
        assert not path.exists()

    def test_doesnt_exist(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'directory'
        assert not path.exists()
        with pytest.raises(FileNotFoundError):
            path.rmdir()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(FileNotFoundError):
            container_path.rmdir()

    def test_file(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'file'
        path.touch()
        with pytest.raises(NotADirectoryError):
            path.rmdir()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(NotADirectoryError):
            container_path.rmdir()

    def test_symlink_to_directory(self, container: ops.Container, tmp_path: pathlib.Path):
        directory = tmp_path / 'directory'
        directory.mkdir()
        symlink = tmp_path / 'symlink'
        symlink.symlink_to(directory)
        with pytest.raises(NotADirectoryError):
            symlink.rmdir()
        container_path = ContainerPath(symlink, container=container)
        with pytest.raises(NotADirectoryError):
            container_path.rmdir()

    def test_not_empty(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'directory'
        path.mkdir()
        (path / 'file').touch()
        with pytest.raises(OSError) as ctx:
            path.rmdir()
        assert ctx.value.errno == errno.ENOTEMPTY
        container_path = ContainerPath(path, container=container)
        with pytest.raises(OSError) as ctx:
            container_path.rmdir()
        assert ctx.value.errno == errno.ENOTEMPTY


class TestUnlink:
    def test_ok(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'file'
        path.touch()
        container_path = ContainerPath(path, container=container)
        container_path.unlink()
        assert not path.exists()

    def test_symlink_to_directory(self, container: ops.Container, tmp_path: pathlib.Path):
        directory = tmp_path / 'directory'
        directory.mkdir()
        symlink = tmp_path / 'symlink'
        # local
        symlink.symlink_to(directory)
        symlink.unlink()
        assert not symlink.exists()
        assert directory.exists()
        # container
        symlink.symlink_to(directory)
        container_path = ContainerPath(symlink, container=container)
        container_path.unlink()
        assert not symlink.exists()
        assert directory.exists()

    def test_doesnt_exist(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'file'
        assert not path.exists()
        with pytest.raises(FileNotFoundError):
            path.unlink()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(FileNotFoundError):
            container_path.unlink()

    def test_doesnt_exist_and_missing_ok(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'file'
        assert not path.exists()
        path.unlink(missing_ok=True)
        container_path = ContainerPath(path, container=container)
        container_path.unlink(missing_ok=True)

    def test_directory(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'directory'
        path.mkdir()
        with pytest.raises(IsADirectoryError):
            path.unlink()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(IsADirectoryError):
            container_path.unlink()


def write_text(path: pathlib.Path | ContainerPath, **kwargs: Any) -> None:
    path.write_text('', **kwargs)
    assert path.read_text() == ''


def write_bytes(path: pathlib.Path | ContainerPath, **kwargs: Any) -> None:
    path.write_bytes(b'', **kwargs)
    assert path.read_bytes() == b''


def mkdir(path: pathlib.Path | ContainerPath, **kwargs: Any) -> None:
    path.mkdir(**kwargs)
    assert path.is_dir()


@pytest.mark.parametrize('method', [pytest.param(fn) for fn in (write_bytes, write_text, mkdir)])
class TestWrite:
    def test_parent_dir_doesnt_exist(
        self, container: ops.Container, tmp_path: pathlib.Path, method: Callable[..., None]
    ):
        parent = tmp_path / 'dirname'
        assert not parent.exists()
        path = parent / 'filename'
        assert not path.exists()
        with pytest.raises(FileNotFoundError):
            method(path)
        container_path = ContainerPath(path, container=container)
        with pytest.raises(FileNotFoundError):
            method(container_path)

    def test_parent_isnt_a_dir(
        self, container: ops.Container, tmp_path: pathlib.Path, method: Callable[..., None]
    ):
        parent = tmp_path / 'parent'
        assert not parent.exists()
        parent.touch()
        assert not parent.is_dir()
        path = parent / 'filename'
        with pytest.raises(NotADirectoryError):
            method(path)
        container_path = ContainerPath(path, container=container)
        with pytest.raises(NotADirectoryError):
            method(container_path)

    def test_user_only_ok(
        self, container: ops.Container, tmp_path: pathlib.Path, method: Callable[..., None]
    ):
        user = getpass.getuser()
        group = grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name
        path = tmp_path / 'filename'
        method(LocalPath(path), user=user)
        assert (path.owner(), path.group()) == (user, group)
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        container_path = ContainerPath(path, container=container)
        method(container_path, user=user)
        assert (path.owner(), path.group()) == (user, group)

    def test_user_and_group_ok(
        self, container: ops.Container, tmp_path: pathlib.Path, method: Callable[..., None]
    ):
        user = getpass.getuser()
        group = grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name
        path = tmp_path / 'filename'
        method(LocalPath(path), user=user, group=group)
        assert (path.owner(), path.group()) == (user, group)
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        container_path = ContainerPath(path, container=container)
        method(container_path, user=user, group=group)
        assert (path.owner(), path.group()) == (user, group)

    def test_group_only_raises_for_container_path(
        self, container: ops.Container, tmp_path: pathlib.Path, method: Callable[..., None]
    ):
        user = getpass.getuser()
        group = grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name
        path = tmp_path / 'filename'
        method(LocalPath(path), group=group)
        assert (path.owner(), path.group()) == (user, group)
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(LookupError):
            method(container_path, group=group)
        assert not path.exists()


@pytest.mark.parametrize(('filename', 'contents'), tuple(utils.BINARY_FILES.items()))
def test_write_bytes(
    container: ops.Container, tmp_path: pathlib.Path, filename: str, contents: bytes
):
    path = tmp_path / filename
    ContainerPath(path, container=container).write_bytes(contents)
    assert path.read_bytes() == contents
    path.write_bytes(contents)
    assert path.read_bytes() == contents


@pytest.mark.parametrize(('filename', 'contents'), tuple(utils.TEXT_FILES.items()))
def test_write_text(
    container: ops.Container, tmp_path: pathlib.Path, filename: str, contents: str
):
    path = tmp_path / filename
    ContainerPath(path, container=container).write_text(contents)
    with path.open(newline='') as f:  # don't translate newlines
        assert f.read() == contents
    path.write_text(contents)
    with path.open(newline='') as f:  # don't translate newlines
        assert f.read() == contents


class TestMkDir:
    def test_ok(self, container: ops.Container, tmp_path: pathlib.Path):
        path = tmp_path / 'dirname'
        assert not path.exists()
        container_path = ContainerPath(path, container=container)
        container_path.mkdir()
        assert path.exists()
        assert path.is_dir()

    @pytest.mark.parametrize('parents', (False, True))
    @pytest.mark.parametrize('filename', utils.FILENAMES)
    def test_file_exists_error(
        self, container: ops.Container, session_dir: pathlib.Path, filename: str, parents: bool
    ):
        path = session_dir / filename
        container_path = ContainerPath(path, container=container)
        path.lstat()  # will fail if there isn't a file there (catches broken links)
        with pytest.raises(FileExistsError):
            path.mkdir(parents=parents)
        with pytest.raises(FileExistsError):
            container_path.mkdir(parents=parents)

    @pytest.mark.parametrize('exist_ok', (False, True))
    def test_file_not_found_error(
        self, container: ops.Container, tmp_path: pathlib.Path, exist_ok: bool
    ):
        parent = tmp_path / 'dirname'
        assert not parent.exists()
        path = parent / 'subdirname'
        assert not path.exists()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(FileNotFoundError):
            path.mkdir(exist_ok=exist_ok)
        with pytest.raises(FileNotFoundError):
            container_path.mkdir(exist_ok=exist_ok)

    @pytest.mark.parametrize('exist_ok', (False, True))
    def test_not_a_directory_error(
        self, container: ops.Container, tmp_path: pathlib.Path, exist_ok: bool
    ):
        parent = tmp_path / 'dirname'
        assert not parent.exists()
        parent.touch()
        assert parent.exists()
        path = parent / 'subdirname'
        assert not path.exists()
        container_path = ContainerPath(path, container=container)
        with pytest.raises(NotADirectoryError):
            path.mkdir(exist_ok=exist_ok)
        with pytest.raises(NotADirectoryError):
            container_path.mkdir(exist_ok=exist_ok)
