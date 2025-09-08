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

"""Tests that don't use a real Pebble to test ContainerPath."""

from __future__ import annotations

import operator
import pathlib
import typing

import ops
import pytest
from ops import pebble

import utils
from charmlibs.pathops import ContainerPath, LocalPath, RelativePathError, _constants, _fileinfo

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


class TestInit:
    def test_ok(self, container: ops.Container):
        ContainerPath('/', container=container)
        ContainerPath(pathlib.Path('/'), container=container)
        ContainerPath(LocalPath('/'), container=container)

    def test_paths_must_be_absolute(self, container: ops.Container):
        assert issubclass(RelativePathError, ValueError)
        with pytest.raises(RelativePathError):
            ContainerPath('.', container=container)
        with pytest.raises(RelativePathError):
            ContainerPath(pathlib.Path('.'), container=container)
        with pytest.raises(RelativePathError):
            ContainerPath(LocalPath('.'), container=container)

    def test_paths_cant_be_container_path(self, container: ops.Container):
        container_path = ContainerPath('/', container=container)
        with pytest.raises(TypeError):
            ContainerPath(container_path, container=container)  # pyright: ignore[reportArgumentType]


#####################
# pure path methods #
#####################


def test_hash(container: ops.Container):
    paths = ('/foo', '/foo/bar', '/foo/bar/byte')
    di = {ContainerPath(path, container=container): path for path in paths}
    for path in paths:
        assert di[ContainerPath(path, container=container)] == path


def test_str(container: ops.Container):
    path = pathlib.Path('/foo/bar')
    container_path = ContainerPath(path, container=container)
    assert pathlib.Path(str(container_path)) == path
    assert pathlib.Path(container_path.as_posix()) == path
    assert str(container_path) == str(path)
    assert container_path.as_posix() == path.as_posix()


def test_repr(container: ops.Container):
    path = pathlib.Path('/foo/bar')
    container_path = ContainerPath(path, container=container)
    result = repr(container_path)
    assert result.startswith('ContainerPath(')
    assert result.endswith(')')


class TestComparison:
    @pytest.mark.parametrize(
        ('left', 'right'),
        (
            ('/foo', '/bar'),
            ('/foo', '/foo/bar'),
            ('/foo/bar', '/foo/bartholemew'),
            ('/foo/bar', '/foob/ar'),
        ),
    )
    @pytest.mark.parametrize(
        'operation', (operator.lt, operator.le, operator.gt, operator.ge, operator.eq)
    )
    def test_ok(
        self,
        operation: Callable[[object, object], bool],
        left: str,
        right: str,
        container: ops.Container,
    ):
        container_path = ContainerPath(left, container=container)
        container_result = operation(container_path, container_path.with_segments(right))
        pathlib_result = operation(pathlib.PurePosixPath(left), pathlib.PurePosixPath(right))
        assert container_result == pathlib_result

    def test_not_equals_non_container_path(self, container: ops.Container):
        assert ContainerPath('/', container=container) != LocalPath('/')
        assert ContainerPath('/', container=container) != '/'

    def test_not_equals_different_container(
        self, container: ops.Container, another_container: ops.Container
    ):
        container_path = ContainerPath('/', container=container)
        another_container_path = ContainerPath('/', container=another_container)
        assert container_path != another_container_path

    @pytest.mark.parametrize('operation', (operator.lt, operator.le, operator.gt, operator.ge))
    def test_inequality_containers_must_be_same(
        self,
        operation: Callable[[object, object], bool],
        container: ops.Container,
        another_container: ops.Container,
    ):
        with pytest.raises(TypeError):
            operation(
                ContainerPath('/', container=container),
                ContainerPath('/', container=another_container),
            )

    @pytest.mark.parametrize('operation', (operator.lt, operator.le, operator.gt, operator.ge))
    def test_inequality_other_cant_be_path_or_str(
        self, operation: Callable[[object, object], bool], container: ops.Container
    ):
        with pytest.raises(TypeError):
            operation(ContainerPath('/', container=container), LocalPath('/'))
        with pytest.raises(TypeError):
            operation(ContainerPath('/', container=container), pathlib.Path('/'))
        with pytest.raises(TypeError):
            operation(ContainerPath('/', container=container), '/')


class TestTrueDiv:
    @pytest.mark.parametrize(
        ('left', 'right'),
        (
            ('/', 'foo'),
            ('/foo', 'foo/bar'),
            ('/foo/bar', 'bartholemew'),
            ('/foo/bar', '/foo/bartholemew'),
        ),
    )
    def test_ok(self, left: str, right: str, container: ops.Container):
        pathlib_path = pathlib.Path(left)
        container_path = ContainerPath(left, container=container)
        assert str(container_path / right) == str(pathlib_path / right)
        assert str(container_path / pathlib.Path(right)) == str(pathlib_path / pathlib.Path(right))
        assert str(container_path / LocalPath(right)) == str(pathlib_path / LocalPath(right))

    def test_rhs_cant_be_container_path(self, container: ops.Container):
        container_path = ContainerPath('/foo', container=container)
        with pytest.raises(TypeError):
            '/foo' / container_path  # type: ignore
        with pytest.raises(TypeError):
            pathlib.Path('/foo') / container_path  # type: ignore
        with pytest.raises(TypeError):
            LocalPath('/foo') / container_path  # type: ignore
        with pytest.raises(TypeError):
            container_path / container_path  # type: ignore


def test_is_absolute(container: ops.Container):
    assert ContainerPath('/', container=container).is_absolute()
    # no further tests needed unless the case below fails
    # which will mean we've added relative path support
    with pytest.raises(RelativePathError):
        ContainerPath('.', container=container)


class TestMatch:
    @pytest.mark.parametrize('path_str', ('/', '/foo', '/foo/bar.txt', '/foo/bar_txt'))
    @pytest.mark.parametrize('pattern', ('', '*', '**/bar', '/foo/bar*', '*.txt', '/FoO/bAr.txt'))
    def test_ok(self, path_str: str, pattern: str, container: ops.Container):
        container_path = ContainerPath(path_str, container=container)
        pathlib_path = pathlib.Path(path_str)
        try:
            pathlib_result = pathlib_path.match(pattern)
        except ValueError:
            with pytest.raises(ValueError):
                container_path.match(pattern)
        else:
            assert container_path.match(pattern) == pathlib_result

    def test_pattern_is_case_sensitive(self, container: ops.Container):
        pattern = '/foo/bar.txt'
        path = pathlib.Path(pattern)
        assert path.match(pattern)
        assert not path.match(pattern.upper())
        container_path = ContainerPath(path, container=container)
        assert container_path.match(pattern)
        assert not container_path.match(pattern.upper())

    def test_pattern_cant_be_container_path(self, container: ops.Container):
        container_path = ContainerPath('/', container=container)
        with pytest.raises(TypeError):
            container_path.match(container_path)  # type: ignore


def test_with_name(container: ops.Container):
    name = 'baz'
    path = pathlib.PurePath('/foo/bar.txt')
    container_path = ContainerPath(path, container=container)
    pathlib_result = path.with_name(name)
    container_result = container_path.with_name(name)
    assert str(container_result) == str(pathlib_result)


class TestWithSuffix:
    def test_ok(self, container: ops.Container):
        suffix = '.bin'
        path = pathlib.PurePath('/foo/bar.txt')
        container_path = ContainerPath(path, container=container)
        pathlib_result = path.with_suffix(suffix)
        container_result = container_path.with_suffix(suffix)
        assert str(container_result) == str(pathlib_result)

    def test_bad_suffix(self, container: ops.Container):
        suffix = 'bin'  # no leading '.'
        path = pathlib.PurePath('/foo/bar.txt')
        container_path = ContainerPath(path, container=container)
        with pytest.raises(ValueError):
            path.with_suffix(suffix)
        with pytest.raises(ValueError):
            container_path.with_suffix(suffix)


class TestJoinPath:
    def test_ok(self, container: ops.Container):
        other = ('bar', 'baz')
        path = pathlib.PurePath('/foo')
        pathlib_result = path.joinpath(*other)
        container_path = ContainerPath(path, container=container)
        container_result = container_path.joinpath(*other)
        assert str(container_result) == str(pathlib_result)

    def test_other_cant_be_container_path(self, container: ops.Container):
        path = pathlib.PurePath('/foo')
        container_path = ContainerPath(path, container=container)
        with pytest.raises(TypeError):
            path.joinpath(container_path)  # type: ignore
        with pytest.raises(TypeError):
            container_path.joinpath(container_path)  # type: ignore


def test_parents(container: ops.Container):
    path = pathlib.PurePath('/foo/bar/baz')
    pathlib_result = tuple(str(p) for p in path.parents)
    container_path = ContainerPath(path, container=container)
    container_result = tuple(str(p) for p in container_path.parents)
    assert container_result == pathlib_result


def test_parent(container: ops.Container):
    path = pathlib.PurePath('/foo/bar/baz')
    pathlib_result = str(path.parent)
    container_path = ContainerPath(path, container=container)
    container_result = str(container_path.parent)
    assert container_result == pathlib_result


def test_parts(container: ops.Container):
    path = pathlib.PurePath('/foo/bar/baz.txt')
    pathlib_result = path.parts
    container_path = ContainerPath(path, container=container)
    container_result = container_path.parts
    assert container_result == pathlib_result


def test_name(container: ops.Container):
    path = pathlib.PurePath('/foo.txt')
    pathlib_result = path.name
    container_path = ContainerPath(path, container=container)
    container_result = container_path.name
    assert container_result == pathlib_result


def test_suffix(container: ops.Container):
    path = pathlib.PurePath('/foo.txt.zip')
    pathlib_result = path.suffix
    container_path = ContainerPath(path, container=container)
    container_result = container_path.suffix
    assert container_result == pathlib_result


def test_suffixes(container: ops.Container):
    path = pathlib.PurePath('/foo.txt.zip')
    pathlib_result = path.suffixes
    container_path = ContainerPath(path, container=container)
    container_result = container_path.suffixes
    assert container_result == pathlib_result


def test_stem(container: ops.Container):
    path = pathlib.PurePath('/foo.txt.zip')
    pathlib_result = path.stem
    container_path = ContainerPath(path, container=container)
    container_result = container_path.stem
    assert container_result == pathlib_result


#########################
# concrete path methods #
#########################


def test_exists_reraises_unhandled_os_error(
    monkeypatch: pytest.MonkeyPatch, container: ops.Container
):
    monkeypatch.setattr(_fileinfo, 'from_container_path', utils.raise_unknown_os_error)
    with pytest.raises(OSError):
        ContainerPath('/', container=container).exists()


@pytest.mark.parametrize(
    ('path_method', 'container_method', 'args', 'kwargs'),
    (
        ('read_bytes', 'pull', (), {}),
        ('read_text', 'pull', (), {}),
        ('is_symlink', 'list_files', (), {}),
        ('rmdir', 'list_files', (), {}),
        ('unlink', 'list_files', (), {}),
        ('_remove_path', 'remove_path', (), {}),
        ('write_bytes', 'list_files', (b'',), {}),
        ('write_bytes', 'push', (b'',), {'mode': _constants.DEFAULT_WRITE_MODE, 'user': ''}),
        ('write_text', 'list_files', ('',), {}),
        ('write_text', 'push', ('',), {'mode': _constants.DEFAULT_WRITE_MODE, 'user': ''}),
        ('mkdir', 'make_dir', (), {}),
    ),
)
@pytest.mark.parametrize(
    ('mock', 'error'),
    (
        (utils.raise_connection_error, pebble.ConnectionError),
        (utils.raise_unknown_path_error, pebble.PathError),
        (utils.raise_permission_denied, PermissionError),
    ),
)
def test_methods_handle_or_reraise_pebble_errors(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
    mock: Callable[[Any], None],
    error: type[Exception],
    path_method: str,
    container_method: str,
    args: tuple[object],
    kwargs: dict[str, object],
):
    monkeypatch.setattr(container, container_method, mock)
    containerpath_method = getattr(ContainerPath, path_method)
    with pytest.raises(error):
        containerpath_method(ContainerPath('/', container=container), *args, **kwargs)


@pytest.mark.parametrize(
    'attr',
    (
        '__rtruediv__',
        '__fspath__',
        '__bytes__',
        'as_uri',
        'relative_to',
        'rglob',
        'stat',
        'lstat',
        'is_mount',
        'is_block_device',
        'is_char_device',
        'chmod',
        'lchmod',
        'symlink_to',
        'resolve',
        'samefile',
        'open',
        'touch',
    ),
)
def test_not_provided(attr: str):
    assert hasattr(pathlib.Path, attr)
    assert not hasattr(ContainerPath, attr)
