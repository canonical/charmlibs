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

"""Type-checking exclusive definitions."""

from __future__ import annotations

import typing

from . import _constants

if typing.TYPE_CHECKING:
    import os
    from collections.abc import Generator, Sequence

    from typing_extensions import Self


# based on typeshed.stdlib.pathlib.PurePath
# https://github.com/python/typeshed/blob/main/stdlib/pathlib.pyi#L29
class PathProtocol(typing.Protocol):
    """The protocol implemented by :class:`ContainerPath` and :class:`LocalPath`.

    Use this class in type annotations where either :class:`ContainerPath` or
    :class:`LocalPath` is acceptable. This will result in both correct type checking
    and useful autocompletions.

    While using a union type will also give correct type checking results, it provides less
    useful autocompletions, as most editors will autocomplete methods and attributes that *any*
    of the union members have, rather than only those that *all* of the union members have.

    :class:`str` follows the :mod:`pathlib` convention and returns the string representation of
    the path. :class:`ContainerPath` return the string representation of the path in the remote
    filesystem. The string representation is suitable for use with system calls (on the correct
    local or remote system) and Pebble layers.

    Comparison methods compare by path. A :class:`ContainerPath` is only comparable to another
    object if it is also a :class:`ContainerPath` on the same :class:`ops.Container`. If this is
    not the case, then equality is ``False`` and other comparisons are :class:`NotImplemented`.

    Protocol implementers are hashable.

    .. warning::
        User implementations of ``PathProtocol`` are not covered by this package's semantic
        versioning promise.

        The semantic versioning of this package reflects the runtime use of :class:`ContainerPath`
        and :class:`LocalPath`. ``PathProtocol`` is always updated to reflect the latest changes to
        :class:`ContainerPath` and :class:`LocalPath`.

        ``PathProtocol`` will always be a valid type annotation for :class:`ContainerPath`,
        :class:`LocalPath`, and :class:`pathlib.PosixPath` objects. However, user implementations
        of ``PathProtocol`` may experience type checking breakage on minor version bumps of this
        package.
    """

    #############################
    # protocol PurePath methods #
    #############################

    def __hash__(self) -> int: ...

    # comparison methods
    def __lt__(self, other: Self) -> bool: ...

    def __le__(self, other: Self) -> bool: ...

    def __gt__(self, other: Self) -> bool: ...

    def __ge__(self, other: Self) -> bool: ...

    def __eq__(self, other: object, /) -> bool: ...

    def __truediv__(self, key: str | os.PathLike[str]) -> Self:
        """Return a new instance of the same type, with the other operand appended to its path.

        Used as ``protocol_implementor / str_or_pathlike``.

        .. note::
            ``__rtruediv__`` is currently not part of this protocol, as
            :class:`ContainerPath` objects only support absolute paths.
        """
        ...

    def __str__(self) -> str: ...

    def as_posix(self) -> str:
        """Return the string representation of the path.

        Exactly like :class:`pathlib.Path` for local paths. Following this convention,
        remote filesystem paths such as :class:`ContainerPath` return the string representation
        of the path in the remote filesystem. The string representation is suitable for
        use with system calls (on the correct local or remote system) and Pebble layers.

        Identical to :class:`str`, since we only support posix systems.
        """
        ...

    def is_absolute(self) -> bool:
        """Return whether the path is absolute (has a root).

        .. note::
            Currently always ``True`` for :class:`ContainerPath`.
        """
        ...

    # NOTE: Not supported -- (Python 3.12) ``case_sensitive`` keyword argument
    def match(self, path_pattern: str) -> bool:
        """Return whether this path matches the given pattern.

        If the pattern is relative, matching is done from the right; otherwise, the entire path is
        matched. The recursive wildcard ``'**'`` is **not** supported by this method. Matching is
        always case-sensitive.
        """
        ...

    def with_name(self, name: str) -> Self:
        """Return a new instance of the same type, with the path name replaced.

        The name is the last component of the path, including any suffixes.
        """
        ...

    def with_suffix(self, suffix: str) -> Self:
        """Return a new instance of the same type, with the path suffix replaced.

        Args:
            suffix: Must start with a ``'.'``, unless it is an empty string, in which case
                any existing suffix will be removed entirely.

        Returns:
            A new instance of the same type, updated as follows. If it contains no ``'.'``,
            or ends with a ``'.'``, the ``suffix`` argument is appended to its name. Otherwise,
            the last ``'.'`` and any trailing content is replaced with the ``suffix`` argument.
        """
        ...

    def joinpath(self, *other: str | os.PathLike[str]) -> Self:
        """Return a new instance of the same type, with its path joined with the arguments.

        Args:
            other: Any number of :class:`str` or :class:`os.PathLike` objects.

        Returns:
            A new instance of the same type, updated as follows. For each item in other,
            if it is a relative path, it is appended to the current path. If it is an absolute
            path, it replaces the current path.

        .. warning::
            :class:`ContainerPath` is not :class:`os.PathLike`. A :class:`ContainerPath` instance
            is not a valid value for ``other``, and will result in an error.
        """
        ...

    @property
    def parents(self) -> Sequence[Self]:
        """A sequence of this path's logical parents. Each parent is an instance of this type."""
        ...

    @property
    def parent(self) -> Self:
        """The logical parent of this path. An instance of this type."""
        ...

    @property
    def parts(self) -> tuple[str, ...]:
        """A sequence of the components in the filesystem path."""
        ...

    @property
    def name(self) -> str:
        """The final path component, or an empty string if this is the root path."""
        ...

    @property
    def suffix(self) -> str:
        """The path name's last suffix (if it has any) including the leading ``'.'``.

        If the path name doesn't have a suffix, the result is an empty string.
        """
        ...

    @property
    def suffixes(self) -> list[str]:
        r"""A list of the path name's suffixes.

        Each suffix includes the leading ``'.'``.

        If the path name doesn't have any suffixes, the result is an empty list.
        """
        ...

    @property
    def stem(self) -> str:
        """The path name, minus its last suffix.

        Where :meth:`name` == :meth:`stem` + :meth:`suffix`
        """
        ...

    #########################
    # protocol Path methods #
    #########################

    # NOTE: Not supported -- (Python 3.13) ``newline`` argument
    def read_text(self) -> str:
        """Read the corresponding local or remote filesystem path and return the string contents.

        Compared to :meth:`pathlib.Path.read_text`, this method drops the ``encoding`` and
        ``errors`` args to simplify the API.

        Returns:
            The UTF-8 decoded contents of the file as a :class:`str`.

        Raises:
            FileNotFoundError: If this path does not exist.
            PermissionError: If the local or remote user does not have read permissions.
            UnicodeError: If the file's contents are not valid UTF-8.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def read_bytes(self) -> bytes:
        """Read the corresponding local or remote filesystem path and return the binary contents.

        Returns:
            The file's raw contents as :class:`bytes`.

        Raises:
            FileNotFoundError: If this path does not exist.
            PermissionError: If the local or remote user does not have read permissions.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def iterdir(self) -> Generator[Self]:
        """Yield objects of the same type corresponding to the directory's contents.

        There are no guarantees about the order of the children. The special entries
        ``'.'`` and ``'..'`` are not included.

        Raises:
            FileNotFoundError: If this path does not exist.
            NotADirectoryError: If this path is not a directory.
            PermissionError: If the local or remote user does not have appropriate permissions.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    # NOTE: Not supported -- (Python 3.12) ``case_sensitive`` argument
    # NOTE: Not supported -- (Python 3.13) ``pattern`` can be path-like
    # NOTE: Not supported -- (Python 3.13) ``recurse_symlinks``
    def glob(self, pattern: str) -> Generator[Self]:
        r"""Iterate over this directory and yield all paths matching the provided pattern.

        For example, ``path.glob('*.txt')``, ``path.glob('*/foo.txt')``.

        .. warning::
            Recursive matching, using the ``'**'`` pattern, is not supported by
            :meth:`ContainerPath.glob`.

        Args:
            pattern: Must be relative, meaning it cannot begin with ``'/'``.
                Matching is case-sensitive.

        Returns:
            A generator yielding objects of the same type as this path, corresponding to those
            of its children which match the pattern. If this path is not a directory, there will
            be no matches.

        Raises:
            FileNotFoundError: If this path does not exist.
            NotImplementedError: If pattern is an absolute path, or (in the case of
                :class:`ContainerPath`) if it uses the ``'**'`` pattern.
            PermissionError: If the local or remote user does not have appropriate permissions.
            ValueError: If the pattern is invalid.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def owner(self) -> str:
        """Return the user name of the file owner.

        Raises:
            FileNotFoundError: If the path does not exist.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def group(self) -> str:
        """Return the group name of the file.

        Raises:
            FileNotFoundError: If the path does not exist.
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    # NOTE: Not supported -- (Python 3.12) ``follow_symlinks`` argument (default=True)
    def exists(self) -> bool:
        """Whether this path exists.

        Will follow symlinks to determine if the symlink target exists. This means that this
        method will return ``False`` for a broken symlink.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    # NOTE: Not supported -- (Python 3.13) ``follow_symlinks`` argument (default=True)
    def is_dir(self) -> bool:
        """Whether this path exists and is a directory.

        Will follow symlinks to determine if the symlink target exists and is a directory.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    # NOTE: Not supported -- (Python 3.13) ``follow_symlinks`` argument (default=True)
    def is_file(self) -> bool:
        """Whether this path exists and is a regular file.

        Will follow symlinks to determine if the symlink target exists and is a regular file.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def is_fifo(self) -> bool:
        """Whether this path exists and is a named pipe (also called a FIFO).

        Will follow symlinks to determine if the symlink target exists and is a named pipe.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def is_socket(self) -> bool:
        """Whether this path exists and is a socket.

        Will follow symlinks to determine if the symlink target exists and is a socket.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def is_symlink(self) -> bool:
        """Whether this path is a symbolic link.

        Raises:
            PebbleConnectionError: If the remote container cannot be reached.
        """
        ...

    def rmdir(self) -> None:
        """Remove this path if it is an empty directory.

        Raises:
            FileNotFoundError: if the path does not exist.
            NotADirectoryError: if the path exists but is not a directory.
            PermissionError: if the local or remote user does not have the appropriate permissions.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        ...

    def unlink(self, missing_ok: bool = False) -> None:
        """Remove this path if it is not a directory.

        Raises:
            FileNotFoundError: if the path does not exist and ``missing_ok`` is false.
            IsADirectoryError: if the path exists but is a directory.
            PermissionError: if the local or remote user does not have the appropriate permissions.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        ...

    ##################################################
    # protocol Path methods with extended signatures #
    ##################################################

    def write_bytes(
        self,
        data: bytes,
        *,
        mode: int | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> int:
        """Write the provided data to the corresponding path.

        Compared to :meth:`pathlib.Path.write_bytes`, this method adds ``mode``, ``user``
        and ``group`` args, which are set on file creation.

        Args:
            data: The bytes to write, typically a :class:`bytes` object, but may also be a
                :class:`bytearray` or :class:`memoryview`.
            mode: The permissions to set on the file. Defaults to 0o644 (-rw-r--r--) for new files.
                If the file already exists, its permissions will be changed,
                unless ``mode`` is ``None`` (default).
            user: The name of the user to set for the directory.
                If ``group`` isn't provided, the user's default group is used.
                If the file already exists, its user and group will be changed,
                unless ``user`` is ``None`` (default).
            group: The name of the group to set for the directory. For :class:`ContainerPath`,
                it is an error to provide ``group`` if ``user`` isn't provided.
                If the file already exists, its group will be changed,
                unless ``user`` and ``group`` are ``None`` (default).

        Returns:
            The number of bytes written.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            LookupError: if the user or group is unknown, or a group is provided without a user.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        ...

    # NOTE: Not supported -- (Python 3.10) ``newline`` argument
    def write_text(
        self,
        data: str,
        *,
        mode: int | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> int:
        """Write the provided string to the corresponding path.

        Compared to :meth:`pathlib.Path.write_text`, this method drops the ``encoding`` and
        ``errors`` args to simplify the API. This method adds ``mode``, ``user`` and ``group``
        args, which are set on file creation.

        Args:
            data: The string to write. Newlines are not modified on writing.
            mode: The permissions to set on the file. Defaults to 0o644 (-rw-r--r--) for new files.
                If the file already exists, its permissions will be changed,
                unless ``mode`` is ``None`` (default).
            user: The name of the user to set for the directory.
                If ``group`` isn't provided, the user's default group is used.
                If the file already exists, its user and group will be changed,
                unless ``user`` is ``None`` (default).
            group: The name of the group to set for the directory. For :class:`ContainerPath`,
                it is an error to provide ``group`` if ``user`` isn't provided.
                If the file already exists, its group will be changed,
                unless ``user`` and ``group`` are ``None`` (default).

        Returns:
            The number of bytes written.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            LookupError: if the user or group is unknown, or a group is provided without a user.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the user does not have permissions for the operation.
            UnicodeError: if the provided data is not valid UTF-8.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        ...

    def mkdir(
        self,
        mode: int = _constants.DEFAULT_MKDIR_MODE,
        parents: bool = False,
        exist_ok: bool = False,
        *,
        user: str | None = None,
        group: str | None = None,
    ) -> None:
        """Create a new directory at the corresponding path.

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
            group: The name of the group to set for the directory. For :class:`ContainerPath`,
                it is an error to provide ``group`` if ``user`` isn't provided.
                The user and group are not changed if the directory already exists.

        Raises:
            FileExistsError: if the directory already exists and ``exist_ok`` is ``False``.
            FileNotFoundError: if the parent directory does not exist and ``parents`` is ``False``.
            LookupError: if the user or group is unknown, or a group is provided without a user.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the local user does not have permissions for the operation.
            PebbleConnectionError: if the remote Pebble client cannot be reached.
        """
        ...


################################################
# pathlib methods not included in the protocol #
################################################

# TODO: clean up these comments structurally and informationally

#############################
# protocol PurePath methods #
#############################

# constructors
# ContainerPath constructor will differ from pathlib.Path constructor
# not part of the protocol
# def __new__(cls, *args: _StrPath, **kwargs: object) -> Self: ...
#  __new__ signature is version dependent
# def __init__(self, *args): ...

# def __reduce__(self): ...
# ops.Container isn't pickleable itself, but we can provide a custom constructor
# for ContainerPath that works with the unpickling protocol, and will attempt to
# make a Container object connected to the appropriate pebble socket
# for simplicity this will be omitted from v1 unless requested

# def __rtruediv__(self, key: str | os.PathLike[str]) -> Self: ...
# omitted from v1 protocol
# doesn't seem worth supporting until (if) ContainerPath gets relative paths
#
# when we have relative paths, it will be meaningful to support the following:
# def __truediv__(self, key: str | os.PathLike[str] | Self) -> Self: ...
# def __rtruediv__(self, key: str | os.PathLike[str] | Self) -> Self: ...
# `ContainerPath / (str or pathlib.Path)`, or `(str or pathlib.Path) / containerPath`
# will result in a new ContainerPath with the same container.
# `ContainerPath / ContainerPath` is an error if the containers are not the same,
# otherwise it too results in a new ContainerPath with the same container.

# def __fspath__(self) -> str: ...
# we don't want ContainerPath to be os.PathLike

# def __bytes__(self) -> bytes: ...
# we don't want ContainerPath to be mistakenly used like a pathlib.Path

# URIs
# this doesn't seem useful and is potentially confusing,so it won't be implemented
# likewise, the constructor (added in 3.13) won't be implemented
# def as_uri(self) -> str: ...
# @classmethod
# def from_uri(uri: str) -> Self: ...

# def is_reserved(self) -> bool: ...
# this will always return False with a PosixPath. Since we assume a Linux container
# so let's just drop it from the protocol for now

# def full_match(self, pattern: str, * case_sensitive: bool = False) -> bool: ...
# 3.13+
# not part of the protocol but may eventually be provided on ContainerPath
# to ease compatibility with pathlib.Path on 3.13+

# def relative_to(self, other: _StrPath, /) -> Self: ...
# this produces relative paths, which we shouldn't be using in any code designed to
# be compatible with both machines and containers, since pebble will error on any
# relative paths at runtime -- if users want to work with relative paths, I think
# they should explicitly work with a PurePath rather than a ContainerPath, and then
# construct the ContainerPath when they have the absolute path they need
#
# Python 3.12 deprecates the below signature, to be dropped in 3.14
# def relative_to(self, *other: _StrPath) -> Self: ...
# to ease future compatibility, we'd just drop support for the old signature
# from the protocol now if it was included
#
# Python 3.12 further modifies the signature with an additional keyword argument
# def relative_to(self, other: _StrPath, walk_up: bool = False) -> Self: ...
# this would not part of the protocol but could eventually be provided on
# ContainerPath to ease compatibility with pathlib.Path on 3.12+ if we someday
# support relative paths

# def is_relative_to(self, other: _StrPath) -> Self: ...  # 3.9+
# not part of protocol but can be provided on ContainerPath implementation
# to ease compatibility with pathlib.Path on 3.9+

# def with_stem(self, stem: str) -> Self: ...  # 3.9+
# not part of protocol but can be provided on ContainerPath implementation
# to ease compatibility with pathlib.Path on 3.9+
# could be added to the protocol if we're happy for LocalPath to double as backports

# def with_segments(self, *pathsegments: _StrPath) -> Self: ...
# required for 3.12+ subclassing machinery
# not part of the protocol (otherwise LocalPath would have to backport it)
# but it is a useful method -- given a ContainerPath with some container,
# you can make another path with the same container cleanly, so it'll be implemented
# on ContainerPath

# @property
# def drive(self) -> str: ...
# will always be '' for Posix -- maybe drop it from the protocol
# so users get more useful autocompletions?

# @property
# def root(self) -> str: ...
# potentially error prone -- ContainerPath.root / Path('foo') is not a ContainerPath

# @property
# def anchor(self) -> str: ...
# this is drive + root

#########################
# protocol Path methods #
#########################

# recursive glob is problematic because Pebble doesn't tell us whether something is a symlink
# so we can easily recurse until we hit Pebble's api limit
# def rglob(
#     self,
#     pattern: str,  # support for _StrPath added in 3.13
#     # *,
#     # case_sensitive: bool = False,  # added in 3.12
#     # recurse_symlinks: bool = False,  # added in 3.13
# ) -> Generator[Self]: ...

# walk was only added in 3.12 -- let's not support this for now, as we'd need to
# implement the walk logic for LocalPath as well as whatever we do for ContainerPath
# (which will also be a bit trickier being unable to distinguish symlinks as dirs)
# While Path.walk wraps os.walk, there are still ~30 lines of pathlib code we'd need
# to vendor for LocalPath.walk
# def walk(
#     self,
#     top_down: bool = True,
#     on_error: typing.Callable[[OSError], None] | None = None,
#     follow_symlinks: bool = False,  # NOTE: ContainerPath runtime error if True
# ) -> typing.Iterator[tuple[Self, list[str], list[str]]]:
#     # TODO: if we add a follow_symlinks option to Pebble's list_files API, we can
#     #       then support follow_symlinks=True on supported Pebble (Juju) versions
#     ...

# def stat(self) -> os.stat_result: ...
# stat follows symlinks to return information about the target
# this may not be in v1, because we can only provide best effort completion on the
# pebble side -- for example, we can't distinguish block and char devices, and we can't
# detect if something is a symlink. Maybe we can provide a top-level fileinfo helper

# def lstat(self) -> os.stat_result: ...
# lstat tells you about the symlink rather than its target
# pebble only tells you about the target
# TODO: support if we add follow_symlinks to Pebble's list_files API

# def is_mount(self) -> bool: ...
# pebble doesn't support this

# def is_junction(self) -> bool: ...
# 3.12
# this will always be False in ContainerPath since we assume a Linux container
# so let's just drop it from the protocol for now

# is_block_device and is_char_device are problematic because pebble only tells us if
# it's a device at all. We can provide an is_device module level helper if needed.
# def is_block_device(self) -> bool: ...
# def is_char_device(self) -> bool: ...

################################################################################
# these concrete methods are currently ruled out due to lack of Pebble support #
################################################################################

# def chmod
# pebble sets mode on creation
# can't provide a separate method
# needs to be argument for other functions
# (same treatment needed for chown)

# link creation, modification, target retrieval
# pebble doesn't support link manipulation
# def hardlink_to
# def symlink_to
# def lchmod
# def readlink
# def resolve

# def samefile
# pebble doesn't return device and i-node number
# can't provide the same semantics

# def open
# the semantics would be different due to needing to make a local copy

# def touch
# would have to pull down the existing file and push it back up just to set mtime

##################
# relative paths #
##################

# OPINION: we shouldn't support relative paths in v1 (if ever)
#
# if we support relative paths, we'd need to implicitly call absolute before every
# call that goes to pebble, and it's not clear whether it's a good idea to implement
# cwd, which absolute would depend on -- we'd have to pebble exec cwd, which wouldn't
# work in certain images (bare rocks)
#
# I think it would be fine for v1 to only support absolute paths, raising an error
# on file operations with relative paths

# the following methods would require us to either hardcode cwd or use a pebble.exec
# def cwd
# typically /root in container
# do we need to query this each time? can we hardcode it?
# def absolute
# interpret relative to cwd

# the following methods would require us to either hardcode home or use a pebble.exec
# def home
# typically /root in container
# do we need to query this each time? can we hardcode it?
# def expanduser
# '~' in parts becomes self.home
