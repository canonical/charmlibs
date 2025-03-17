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
from charmlibs.pathops import ContainerPath, LocalPath, RelativePathError, _fileinfo

if typing.TYPE_CHECKING:
    from typing import Any, Callable


class TestInit:
    def test_ok(self, container: ops.Container):
        ContainerPath('/', container=container)
        ContainerPath(pathlib.Path('/'), container=container)
        ContainerPath(LocalPath('/'), container=container)

    def test_given_relative_path_then_raises(self, container: ops.Container):
        assert issubclass(RelativePathError, ValueError)
        with pytest.raises(RelativePathError):
            ContainerPath('.', container=container)
        with pytest.raises(RelativePathError):
            ContainerPath(pathlib.Path('.'), container=container)
        with pytest.raises(RelativePathError):
            ContainerPath(LocalPath('.'), container=container)

    def test_given_container_path_then_raises(self, container: ops.Container):
        container_path = ContainerPath('/', container=container)
        with pytest.raises(TypeError):
            ContainerPath(container_path, container=container)  # pyright: ignore[reportArgumentType]


#####################
# pure path methods #
#####################


class TestHash:
    def test_ok(self, container: ops.Container):
        paths = ('/foo', '/foo/bar', '/foo/bar/byte')
        di = {ContainerPath(path, container=container): path for path in paths}
        for path in paths:
            assert di[ContainerPath(path, container=container)] == path


class TestStr:
    def test_ok(self, container: ops.Container):
        path = pathlib.Path('/foo/bar')
        container_path = ContainerPath(path, container=container)
        assert pathlib.Path(str(container_path)) == path
        assert pathlib.Path(container_path.as_posix()) == path
        assert str(container_path) == str(path)
        assert container_path.as_posix() == path.as_posix()


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

    def test_when_other_isnt_container_path_then_equality_returns_false(
        self, container: ops.Container
    ):
        assert ContainerPath('/', container=container) != LocalPath('/')
        assert ContainerPath('/', container=container) != '/'

    def test_when_containers_are_different_then_equality_returns_false(
        self, container: ops.Container, another_container: ops.Container
    ):
        container_path = ContainerPath('/', container=container)
        another_container_path = ContainerPath('/', container=another_container)
        assert container_path != another_container_path

    @pytest.mark.parametrize('operation', (operator.lt, operator.le, operator.gt, operator.ge))
    def test_when_containers_are_different_then_inequality_raises_type_error(
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
    def test_when_other_isnt_container_path_then_inequality_raises_type_error(
        self, operation: Callable[[object, object], bool], container: ops.Container
    ):
        with pytest.raises(TypeError):
            operation(ContainerPath('/', container=container), LocalPath('/'))
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

    def test_when_container_path_is_right_hand_side_then_truediv_raises_type_error(
        self, container: ops.Container
    ):
        container_path = ContainerPath('/foo', container=container)
        with pytest.raises(TypeError):
            '/foo' / container_path  # type: ignore
        with pytest.raises(TypeError):
            pathlib.Path('/foo') / container_path  # type: ignore
        with pytest.raises(TypeError):
            LocalPath('/foo') / container_path  # type: ignore
        with pytest.raises(TypeError):
            container_path / container_path  # type: ignore


class TestIsAbsolute:
    def test_ok(self, container: ops.Container):
        assert ContainerPath('/', container=container).is_absolute()
        # no further tests needed unless the case below fails
        # which will mean we've added relative path support
        with pytest.raises(RelativePathError):
            ContainerPath('.', container=container)


class TestMatch:
    @pytest.mark.parametrize('path_str', ('/', '/foo', '/foo/bar.txt', '/foo/bar_txt'))
    @pytest.mark.parametrize('pattern', ('', '*', '**/bar', '/foo/bar*', '*.txt'))
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

    def test_when_pattern_is_container_path_then_raises_type_error(self, container: ops.Container):
        container_path = ContainerPath('/', container=container)
        with pytest.raises(TypeError):
            container_path.match(container_path)  # type: ignore


class TestWithName:
    def test_ok(self, container: ops.Container):
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

    def test_when_suffix_doesnt_start_with_dot_then_raises_value_error(
        self, container: ops.Container
    ):
        suffix = 'bin'
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

    def test_when_other_is_container_path_then_raises_type_error(self, container: ops.Container):
        path = pathlib.PurePath('/foo')
        container_path = ContainerPath(path, container=container)
        with pytest.raises(TypeError):
            path.joinpath(container_path)  # type: ignore
        with pytest.raises(TypeError):
            container_path.joinpath(container_path)  # type: ignore


class TestParents:
    def test_ok(self, container: ops.Container):
        path = pathlib.PurePath('/foo/bar/baz')
        pathlib_result = tuple(str(p) for p in path.parents)
        container_path = ContainerPath(path, container=container)
        container_result = tuple(str(p) for p in container_path.parents)
        assert container_result == pathlib_result


class TestParent:
    def test_ok(self, container: ops.Container):
        path = pathlib.PurePath('/foo/bar/baz')
        pathlib_result = str(path.parent)
        container_path = ContainerPath(path, container=container)
        container_result = str(container_path.parent)
        assert container_result == pathlib_result


class TestParts:
    def test_ok(self, container: ops.Container):
        path = pathlib.PurePath('/foo/bar/baz.txt')
        pathlib_result = path.parts
        container_path = ContainerPath(path, container=container)
        container_result = container_path.parts
        assert container_result == pathlib_result


class TestName:
    def test_ok(self, container: ops.Container):
        path = pathlib.PurePath('/foo.txt')
        pathlib_result = path.name
        container_path = ContainerPath(path, container=container)
        container_result = container_path.name
        assert container_result == pathlib_result


class TestSuffix:
    def test_ok(self, container: ops.Container):
        path = pathlib.PurePath('/foo.txt.zip')
        pathlib_result = path.suffix
        container_path = ContainerPath(path, container=container)
        container_result = container_path.suffix
        assert container_result == pathlib_result


class TestSuffixes:
    def test_ok(self, container: ops.Container):
        path = pathlib.PurePath('/foo.txt.zip')
        pathlib_result = path.suffixes
        container_path = ContainerPath(path, container=container)
        container_result = container_path.suffixes
        assert container_result == pathlib_result


class TestStem:
    def test_ok(self, container: ops.Container):
        path = pathlib.PurePath('/foo.txt.zip')
        pathlib_result = path.stem
        container_path = ContainerPath(path, container=container)
        container_result = container_path.stem
        assert container_result == pathlib_result


#########################
# concrete path methods #
#########################


@pytest.mark.parametrize('method', ('read_bytes', 'read_text'))
class TestReadCommon:
    @pytest.mark.parametrize(
        ('mock', 'error'),
        (
            (utils.raise_connection_error, pebble.ConnectionError),
            (utils.raise_unknown_path_error, pebble.PathError),
        ),
    )
    def test_unhandled_pebble_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        container: ops.Container,
        mock: Callable[[Any], None],
        error: type[Exception],
        method: str,
    ):
        monkeypatch.setattr(container, 'pull', mock)
        containerpath_method = getattr(ContainerPath, method)
        with pytest.raises(error):
            containerpath_method(ContainerPath('/', container=container))


class TestExists:
    def test_unhandled_os_error(self, monkeypatch: pytest.MonkeyPatch, container: ops.Container):
        monkeypatch.setattr(_fileinfo, 'from_container_path', utils.raise_unknown_os_error)
        with pytest.raises(OSError):
            ContainerPath('/', container=container).exists()


class TestWriteBytes:
    @pytest.mark.parametrize(
        ('mock', 'error'),
        (
            (utils.raise_connection_error, pebble.ConnectionError),
            (utils.raise_unknown_path_error, pebble.PathError),
        ),
    )
    def test_unhandled_pebble_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        container: ops.Container,
        mock: Callable[[Any], None],
        error: type[Exception],
    ):
        monkeypatch.setattr(container, 'push', mock)
        with pytest.raises(error):
            ContainerPath('/', container=container).write_bytes(b'')


class TestMkDir:
    @pytest.mark.parametrize(
        ('mock', 'error'),
        (
            (utils.raise_connection_error, pebble.ConnectionError),
            (utils.raise_unknown_path_error, pebble.PathError),
        ),
    )
    def test_unhandled_pebble_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        container: ops.Container,
        mock: Callable[[Any], None],
        error: type[Exception],
    ):
        monkeypatch.setattr(container, 'make_dir', mock)
        with pytest.raises(error):
            ContainerPath('/', container=container).mkdir()


@pytest.mark.parametrize(
    'attr',
    (
        '__rtruediv__',
        '__fspath__',
        '__bytes__',
        'as_uri',
        'relative_to',
        'rmdir',
        'unlink',
        'rglob',
        'stat',
        'lstat',
        'is_mount',
        'is_symlink',
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
