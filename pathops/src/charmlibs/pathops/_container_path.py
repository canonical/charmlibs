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

"""Implementation of ContainerPath class."""

from __future__ import annotations

import errno
import pathlib
import re
import typing

import ops
from ops import pebble

from . import _constants, _errors, _fileinfo

if typing.TYPE_CHECKING:
    import os
    from collections.abc import Generator
    from typing import Literal, TypeGuard

    from typing_extensions import Self


class RelativePathError(ValueError):
    """ContainerPath only supports absolute paths.

    This is because Pebble only works with absolute paths. Relative path support
    will likely remain unavailable at least until Pebble supports relative paths.
    In the meantime, use absolute paths.
    """


class ContainerPath:
    r"""Implementation of :class:`PathProtocol` for Pebble-based workload containers.

    The following examples are all equivalent::

        container = self.unit.get_container('c')
        ContainerPath('/foo', container=container)
        ContainerPath('/', 'foo', container=container)
        ContainerPath(pathlib.PurePath('/foo'), container=container)
        ContainerPath(pathlib.PurePath('/'), 'foo', container=container)

    :class:`str` follows the :mod:`pathlib` convention and returns the string representation of
    the path. :class:`ContainerPath` return the string representation of the path in the remote
    filesystem. The string representation is suitable for use with system calls (on the correct
    local or remote system) and Pebble layers.

    Comparison methods compare by path. A :class:`ContainerPath` is only comparable to another
    object if it is also a :class:`ContainerPath` on the same :class:`ops.Container`. If this is
    not the case, then equality is ``False`` and other comparisons are :class:`NotImplemented`.

    Args:
        \*parts: components of the path, like :class:`pathlib.Path` constructor.
        container: used to communicate with the workload container. Required.
            Must be provided as a keyword argument.

    Raises:
        RelativePathError: If instantiated with a relative path.
    """

    def __init__(self, *parts: str | os.PathLike[str], container: ops.Container) -> None:
        self._container = container
        self._path = pathlib.PurePosixPath(*parts)
        if not self._path.is_absolute():
            raise RelativePathError(
                f'ContainerPath arguments resolve to relative path: {self._path}'
            )

    #############################
    # protocol PurePath methods #
    #############################

    def __hash__(self) -> int:
        """Hash the tuple (container-name, path) for efficiency."""
        return hash((self._container.name, self._path))

    def __repr__(self) -> str:
        """Return a string representation including the class, path string, and container name."""
        container_repr = f'<ops.Container {self._container.name!r}>'
        return f"{type(self).__name__}('{self._path}', container={container_repr})"

    def __str__(self) -> str:
        """Return the string representation of the path in the container.

        This is equivalent to the string representation of the :class:`pathlib.PurePath` this
        :class:`ContainerPath` was instantiated with.
        """
        return self._path.__str__()

    def as_posix(self) -> str:
        """Return the string representation of the path in the container."""
        return self._path.__str__()

    def __lt__(self, other: Self) -> bool:
        if not self._can_compare(other):
            return NotImplemented
        return self._path < other._path

    def __le__(self, other: Self) -> bool:
        if not self._can_compare(other):
            return NotImplemented
        return self._path <= other._path

    def __gt__(self, other: Self) -> bool:
        if not self._can_compare(other):
            return NotImplemented
        return self._path > other._path

    def __ge__(self, other: Self) -> bool:
        if not self._can_compare(other):
            return NotImplemented
        return self._path >= other._path

    def __eq__(self, other: object, /) -> bool:
        return self._can_compare(other) and self._path == other._path

    def _can_compare(self, other: object) -> TypeGuard[Self]:
        return isinstance(other, ContainerPath) and other._container.name == self._container.name

    def __truediv__(self, key: str | os.PathLike[str]) -> Self:
        """Return a new ``ContainerPath`` with the same container and the joined path.

        The joined path is equivalent to ``str(self) / pathlib.PurePath(key)``.

        .. warning::
            ``__rtruediv__`` is not supported, as :class:`ContainerPath` only supports absolute
            paths. You likely wouldn't want to provide an absolute path as the right-hand operand,
            because the absolute path would completely replace the left-hand path.
        """
        return self.with_segments(self._path, key)

    def is_absolute(self) -> bool:
        """Return whether the path is absolute (has a root), which is always the case.

        Always ``True``, since initialising a :class:`ContainerPath` with a non-absolute
        path will result in a :class:`RelativePathError`.
        """
        return self._path.is_absolute()

    def match(self, path_pattern: str) -> bool:
        """Return whether this path matches the given pattern.

        If the pattern is relative, matching is done from the right; otherwise, the entire path is
        matched. The recursive wildcard ``'**'`` is **not** supported by this method. Matching is
        always case-sensitive. Only the path is matched against, the container is not considered.
        """
        return self._path.match(path_pattern)

    def with_name(self, name: str) -> Self:
        """Return a new ContainerPath, with the same container, but with the path name replaced.

        The name is the last component of the path, including any suffixes.

        ::

            container = self.unit.get_container('c')
            path = ContainerPath('/', 'foo', 'bar.txt', container=container)
            repr(path.with_name('baz.bin'))
            # ContainerPath('/foo/baz.bin', container=<ops.Container 'c'>)"
        """
        return self.with_segments(self._path.with_name(name))

    def with_suffix(self, suffix: str) -> Self:
        """Return a new ContainerPath with the same container and the suffix changed.

        Args:
            suffix: Must start with a ``'.'``, unless it is an empty string, in which case
                any existing suffix will be removed entirely.

        Returns:
            A new instance of the same type, updated as follows. If it contains no ``'.'``,
            or ends with a ``'.'``, the ``suffix`` argument is appended to its name. Otherwise,
            the last ``'.'`` and any trailing content is replaced with the ``suffix`` argument.
        """
        return self.with_segments(self._path.with_suffix(suffix))

    def joinpath(self, *other: str | os.PathLike[str]) -> Self:
        r"""Return a new ContainerPath with the same container and the new args joined to its path.

        Args:
            other: Any number of :class:`str` or :class:`os.PathLike` objects.
                If zero are provided, an effective copy of this :class:`ContainerPath` object is
                returned. \*other is joined to this object's path as with :func:`os.path.join`.
                This means that if any member of other is an absolute path, all the previous
                components, including this object's path, are dropped entirely.

        Returns:
            A new :class:`ContainerPath` with the same :class:`ops.Container` object, with its path
            updated with \*other as follows. For each item in other, if it is a relative path, it
            is appended to the current path. If it is an absolute path, it replaces the current
            path.

        .. warning::
            :class:`ContainerPath` is not :class:`os.PathLike`. A :class:`ContainerPath` instance
            is not a valid value for ``other``, and will result in an error.
        """
        return self.with_segments(self._path, *other)

    @property
    def parents(self) -> tuple[Self, ...]:
        """A sequence of this path's logical parents. Each parent is a :class:`ContainerPath`."""
        return tuple(self.with_segments(p) for p in self._path.parents)

    @property
    def parent(self) -> Self:
        """The logical parent of this path, as a :class:`ContainerPath`."""
        return self.with_segments(self._path.parent)

    @property
    def parts(self) -> tuple[str, ...]:
        """A sequence of the components in the filesystem path. The components are strings."""
        return self._path.parts

    @property
    def name(self) -> str:
        """The final path component, or an empty string if this is the root path."""
        return self._path.name

    @property
    def suffix(self) -> str:
        """The path name's last suffix (if it has any) including the leading ``'.'``.

        If the path name doesn't have a suffix, the result is an empty string.
        """
        return self._path.suffix

    @property
    def suffixes(self) -> list[str]:
        r"""A list of the path name's suffixes.

        Each suffix includes the leading ``'.'``.

        If the path name doesn't have any suffixes, the result is an empty list.
        """
        return self._path.suffixes

    @property
    def stem(self) -> str:
        """The path name, minus its last suffix.

        Where :meth:`name` == :meth:`stem` + :meth:`suffix`
        """
        return self._path.stem

    #########################
    # protocol Path methods #
    #########################

    def read_text(self, *, newline: str | None = None) -> str:
        r"""Read a remote file as text and return the contents as a string.

        Compared to pathlib.Path.read_text, this method drops the encoding and errors args.
        The encoding is assumed to be UTF-8, and any errors encountered will be raised.

        Args:
            newline: if ``None`` (default), all newlines ``('\r\n', '\r', '\n')`` are replaced
                with ``'\n'``. Otherwise the file contents are returned unmodified.

        Returns:
            The contents of the the path as a string.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            IsADirectoryError: if the target is a directory.
            PermissionError: if the Pebble user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        text = self._pull(text=True)
        if newline is None:
            return re.sub(r'\r\n|\r', '\n', text)
        return text

    def read_bytes(self) -> bytes:
        """Read a remote file as bytes and return the contents.

        Returns:
            The contents of the the path as byes.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            IsADirectoryError: if the target is a directory.
            PermissionError: if the Pebble user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        return self._pull(text=False)

    @typing.overload
    def _pull(self, *, text: Literal[True]) -> str: ...
    @typing.overload
    def _pull(self, *, text: Literal[False] = False) -> bytes: ...
    def _pull(self, *, text: bool = False):
        encoding = 'utf-8' if text else None
        try:
            with self._container.pull(self._path, encoding=encoding) as f:
                return f.read()
        except pebble.PathError as e:
            msg = repr(self)
            _errors.raise_if_matches_file_not_found(e, msg=msg)
            _errors.raise_if_matches_is_a_directory(e, msg=msg)
            _errors.raise_if_matches_permission(e, msg=msg)
            raise

    def iterdir(self) -> typing.Generator[Self]:
        """Yield :class:`ContainerPath` objects corresponding to the directory's contents.

        There are no guarantees about the order of the children. The special entries
        ``'.'`` and ``'..'`` are not included.

        :class:`NotADirectoryError` is raised (if appropriate) when ``iterdir()`` is called.
        This follows the behaviour of :meth:`pathlib.Path.iterdir` in Python 3.13+.
        Previous versions deferred the error until the generator was consumed.

        Raises:
            FileNotFoundError: If this path does not exist.
            NotADirectoryError: If this path is not a directory.
            PermissionError: If the local or remote user does not have appropriate permissions.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        info = _fileinfo.from_container_path(self)  # FileNotFoundError if path doesn't exist
        if info.type != pebble.FileType.DIRECTORY:
            _errors.raise_not_a_directory(repr(self))
        file_infos = self._container.list_files(self._path)
        for f in file_infos:
            yield self.with_segments(f.path)

    def glob(self, pattern: str | os.PathLike[str]) -> Generator[Self]:
        r"""Iterate over this directory and yield all paths matching the provided pattern.

        For example, ``path.glob('*.txt')``, ``path.glob('*/foo.txt')``.

        .. warning::
            Recursive matching using the ``'**'`` pattern is not supported.

        Args:
            pattern: The pattern must be relative, meaning it cannot begin with ``'/'``.
                Matching is case-sensitive.

        Returns:
            A generator yielding :class:`ContainerPath` objects, corresponding to those of its
            children which match the pattern. If this path is not a directory, there will be no
            matches.

        Raises:
            FileNotFoundError: If this path does not exist.
            NotImplementedError: If pattern is an absolute path or it uses the ``'**'`` pattern.
            PermissionError: If the remote user does not have appropriate permissions.
            ValueError: If the pattern is invalid.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        return self._glob(pattern)

    def _glob(self, pattern: str | os.PathLike[str], skip_is_dir: bool = False) -> Generator[Self]:
        pattern_path = pathlib.PurePosixPath(pattern)
        if pattern_path.is_absolute():
            raise NotImplementedError('Non-relative paths are unsupported.')
        elif pattern_path == pathlib.PurePosixPath('.'):
            raise ValueError(f'Unacceptable pettern: {pattern!r}')
        *pattern_parents, pattern_itself = pattern_path.parts
        if '**' in pattern_parents:
            raise NotImplementedError('Recursive glob is not supported.')
        if '**' in str(pattern):
            raise ValueError("Invalid pattern: '**' can only be an entire path component")
        if not skip_is_dir and not self.is_dir():
            yield from ()
            return
        if not pattern_parents:
            file_infos = self._container.list_files(self._path, pattern=pattern_itself)
            for f in file_infos:
                yield self.with_segments(f.path)
            return
        first, *rest = pattern_parents
        next_pattern = pathlib.PurePosixPath(*rest, pattern_itself)
        if first == '*':
            for container_path in self.iterdir():
                if container_path.is_dir():
                    yield from container_path._glob(next_pattern, skip_is_dir=True)
        elif '*' in first:
            for container_path in self._glob(first):
                if container_path.is_dir():
                    yield from container_path._glob(next_pattern, skip_is_dir=True)
        else:
            yield from (self / first)._glob(next_pattern)

    def owner(self) -> str:
        """Return the user name of the file owner.

        Raises:
            FileNotFoundError: If the path does not exist.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        info = _fileinfo.from_container_path(self)  # FileNotFoundError if path doesn't exist
        user = info.user
        assert user is not None
        return user

    def group(self) -> str:
        """Return the group name of the file.

        Raises:
            FileNotFoundError: If the path does not exist.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        info = _fileinfo.from_container_path(self)  # FileNotFoundError if path doesn't exist
        group = info.group
        assert group is not None
        return group

    def exists(self) -> bool:
        """Whether this path exists.

        Will follow symlinks to determine if the symlink target exists. This means that this
        method will return ``False`` for a broken symlink.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        return self._exists_and_matches(filetype=None)

    def is_dir(self) -> bool:
        """Whether this path exists and is a directory.

        Will follow symlinks to determine if the symlink target exists and is a directory.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        return self._exists_and_matches(pebble.FileType.DIRECTORY)

    def is_file(self) -> bool:
        """Whether this path exists and is a regular file.

        Will follow symlinks to determine if the symlink target exists and is a regular file.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        return self._exists_and_matches(pebble.FileType.FILE)

    def is_fifo(self) -> bool:
        """Whether this path exists and is a named pipe (also called a FIFO).

        Will follow symlinks to determine if the symlink target exists and is a named pipe.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        return self._exists_and_matches(pebble.FileType.NAMED_PIPE)

    def is_socket(self) -> bool:
        """Whether this path exists and is a socket.

        Will follow symlinks to determine if the symlink target exists and is a socket.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        return self._exists_and_matches(pebble.FileType.SOCKET)

    def is_symlink(self) -> bool:
        """Whether this path is a symbolic link.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        try:
            info = _fileinfo.from_container_path(self, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return info.type == pebble.FileType.SYMLINK

    def _exists_and_matches(self, filetype: pebble.FileType | None) -> bool:
        info = self._try_get_fileinfo()
        if info is None:
            return False
        if filetype is None:  # we only care if the file exists
            return True
        return info.type is filetype

    def _try_get_fileinfo(self) -> pebble.FileInfo | None:
        try:
            return _fileinfo.from_container_path(self)
        except FileNotFoundError:
            pass
        except OSError as e:
            if e.errno != errno.ELOOP:
                raise
            # else: too many levels of symbolic links
        return None

    def rmdir(self) -> None:
        """Remove this path if it is an empty directory.

        Raises:
            FileNotFoundError: if the path does not exist.
            NotADirectoryError: if the path exists but is not a directory.
            PermissionError: if the Pebble user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        info = _fileinfo.from_container_path(self, follow_symlinks=False)
        if info.type != pebble.FileType.DIRECTORY:
            _errors.raise_not_a_directory(repr(self))
        self._remove_path()

    def unlink(self, missing_ok: bool = False) -> None:
        """Remove this path if it is not a directory.

        Raises:
            FileNotFoundError: if the path does not exist and ``missing_ok`` is false.
            IsADirectoryError: if the path exists but is a directory.
            PermissionError: if the Pebble user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        try:
            info = _fileinfo.from_container_path(self, follow_symlinks=False)
        except FileNotFoundError:
            if missing_ok:
                return
            raise
        if info.type == pebble.FileType.DIRECTORY:
            _errors.raise_is_a_directory(repr(self))
        self._remove_path()

    def _remove_path(self) -> None:
        try:
            self._container.remove_path(self._path)
        except pebble.PathError as e:
            msg = repr(self)
            _errors.raise_if_matches_directory_not_empty(e, msg=msg)
            _errors.raise_if_matches_file_not_found(e, msg=msg)
            _errors.raise_if_matches_permission(e, msg=msg)
            raise

    ##################################################
    # protocol Path methods with extended signatures #
    ##################################################

    def write_bytes(
        self,
        data: bytes | bytearray | memoryview,
        *,
        mode: int | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> int:
        """Write the provided data to the corresponding path in the remote container.

        Compared to :meth:`pathlib.Path.write_bytes`, this method adds ``mode``, ``user``
        and ``group`` args. These are forwarded to Pebble, which sets these on file creation.

        Args:
            data: The bytes to write. If data is a :class:`bytearray` or :class:`memoryview`, it
                will be converted to :class:`bytes` in memory first.
            mode: The permissions to set on the file. Defaults to 0o644 (-rw-r--r--) for new files.
                If the file already exists, its permissions will be changed,
                unless ``mode`` is ``None`` (default).
            user: The name of the user to set for the file.
                If ``group`` isn't provided, the user's default group is used.
                If the file already exists, its user and group will be changed,
                unless ``user`` is ``None`` (default).
            group: The name of the group to set for the directory.
                It is an error to provide ``group`` if ``user`` isn't provided.
                If the file already exists, its group will be changed,
                unless ``user`` and ``group`` are ``None`` (default).

        Returns: The number of bytes written.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            LookupError: if the user or group is unknown, or a group is provided without a user.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the Pebble user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        if isinstance(data, (bytearray, memoryview)):
            # TODO: update ops to correctly test for bytearray and memoryview in push
            data = bytes(data)
        if mode is None or user is None:
            # if the file already exists, don't change owner or mode unless explicitly requested
            try:
                info = _fileinfo.from_container_path(self)
            except FileNotFoundError:
                pass
            else:
                if mode is None:
                    mode = info.permissions
                if user is None:
                    user = info.user
        try:
            self._container.push(
                path=self._path,
                source=data,
                make_dirs=False,
                permissions=mode,
                user=user,
                group=group,
            )
        except pebble.PathError as e:
            _errors.raise_if_matches_lookup(e, msg=e.message)
            msg = repr(self)
            _errors.raise_if_matches_file_not_found(e, msg=msg)
            _errors.raise_if_matches_not_a_directory(e, msg=msg)
            _errors.raise_if_matches_permission(e, msg=msg)
            raise
        return len(data)

    def write_text(
        self,
        data: str,
        *,
        mode: int | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> int:
        """Write the provided string to the corresponding path in the remote container.

        Compared to :meth:`pathlib.Path.write_text`, this method drops the ``encoding`` and
        ``errors`` args to simplify the API. The args ``mode``, ``user`` and ``group`` are added,
        and are forwarded to Pebble, which sets these on file creation.

        Args:
            data: The string to write. Will be encoded to :class:`bytes` in memory as UTF-8,
                raising any errors. Newlines are not modified on writing.
            mode: The permissions to set on the file. Defaults to 0o644 (-rw-r--r--) for new files.
                If the file already exists, its permissions will be changed,
                unless ``mode`` is ``None`` (default).
            user: The name of the user to set for the file.
                If ``group`` isn't provided, the user's default group is used.
                If the file already exists, its user and group will be changed,
                unless ``user`` is ``None`` (default).
            group: The name of the group to set for the directory.
                It is an error to provide ``group`` if ``user`` isn't provided.
                If the file already exists, its group will be changed,
                unless ``user`` and ``group`` are ``None`` (default).

        Returns: The number of bytes written.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            LookupError: if the user or group is unknown, or a group is provided without a user.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the Pebble user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        encoded_data = data.encode()
        return self.write_bytes(encoded_data, mode=mode, user=user, group=group)

    def mkdir(
        self,
        mode: int = _constants.DEFAULT_MKDIR_MODE,
        parents: bool = False,
        exist_ok: bool = False,
        *,
        user: str | None = None,
        group: str | None = None,
    ) -> None:
        """Create a new directory at the corresponding path in the remote container.

        Compared to :meth:`pathlib.Path.mkdir`, this method adds ``user`` and ``group`` args.
        These are used to set the ownership of the created directory. Any created parents
        will not have their ownership set.

        Args:
            mode: The permissions to set on the created directory. Any parents created will have
                their permissions set to the default value of 0o755 (drwxr-xr-x).
                The permissions are not changed if the directory already exists.
            parents: Whether to create any missing parent directories as well. If ``False``
                (default) and a parent directory does not exist, a :class:`FileNotFound` error will
                be raised.
            exist_ok: Whether to raise an error if the directory already exists.
                If ``False`` (default) and the directory already exists,
                a :class:`FileExistsError` will be raised.
            user: The name of the user to set for the directory.
                If ``group`` isn't provided, the user's default group is used.
                The user and group are not changed if the directory already exists.
            group: The name of the group to set for the directory.
                It is an error to provide ``group`` if ``user`` isn't provided.
                The user and group are not changed if the directory already exists.

        Raises:
            FileExistsError: if the directory already exists and ``exist_ok`` is ``False``.
            FileNotFoundError: if the parent directory does not exist and ``parents`` is ``False``.
            LookupError: if the user or group is unknown, or a group is provided without a user.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the remote user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        if parents and not exist_ok and self.exists():
            _errors.raise_file_exists(repr(self))
        if exist_ok and not parents and not self.parent.exists():
            _errors.raise_file_not_found(repr(self.parent))
        if parents and mode != _constants.DEFAULT_MKDIR_MODE:
            # create parents with default permissions, following pathlib
            self._mkdir(
                path=self._path.parent,
                make_parents=True,
                permissions=_constants.DEFAULT_MKDIR_MODE,
            )
        self._mkdir(
            path=self._path,
            make_parents=exist_ok or parents,
            permissions=mode,
            user=user,
            group=group,
        )

    def _mkdir(
        self,
        path: str | pathlib.PurePath,
        make_parents: bool,
        permissions: int,
        user: str | None = None,
        group: str | None = None,
    ) -> None:
        try:
            self._container.make_dir(
                path=path,
                make_parents=make_parents,
                permissions=permissions,
                user=user,
                group=group,
            )
        except pebble.PathError as e:
            _errors.raise_if_matches_lookup(e, msg=e.message)
            msg = repr(self)
            if _errors.matches_not_a_directory(e):
                # target exists and isn't a directory, or parent isn't a directory
                if not self.parent.is_dir():
                    _errors.raise_not_a_directory(msg=msg, from_=e)
                _errors.raise_file_exists(repr(self), from_=e)
            _errors.raise_if_matches_file_exists(e, msg=msg)
            _errors.raise_if_matches_file_not_found(e, msg=msg)
            _errors.raise_if_matches_permission(e, msg=msg)
            raise

    #############################
    # non-protocol Path methods #
    #############################

    def with_segments(self, *pathsegments: str | os.PathLike[str]) -> Self:
        """Construct a new ``ContainerPath`` (with the same container) from path-like objects.

        You can think of this like a copy of the current :class:`ContainerPath`, with its path
        replaced by ``pathlib.Path(*pathsegments)``.

        This method is used internally by all :class:`ContainerPath` methods that return new
        :class:`ContainerPath` instances, including :meth:`parent` and :meth:`parents`. Therefore,
        subclasses can customise the behaviour of all such methods by overriding only this method.
        The same is true of :class:`pathlib.Path` in Python 3.12+.
        """
        return type(self)(*pathsegments, container=self._container)
