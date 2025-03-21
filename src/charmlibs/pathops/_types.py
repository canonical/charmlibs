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
    from typing import Generator, Sequence

    from typing_extensions import Self, TypeAlias


Bytes: TypeAlias = 'bytes | bytearray | memoryview'
StrPathLike: TypeAlias = 'str | os.PathLike[str]'


# based on typeshed.stdlib.pathlib.PurePath
# https://github.com/python/typeshed/blob/main/stdlib/pathlib.pyi#L29
class PathProtocol(typing.Protocol):
    """The protocol implemented by :class:`ContainerPath` and :class:`LocalPath`.

    .. tip::
        Use this class in type annotations where either :class:`ContainerPath` or
        :class:`LocalPath` is acceptable. This will result in both correct type checking
        and useful autocompletions. Using a union type instead will give correct type checking
        results, but will autocomplete methods that only *either* of the unions members have.
    """

    #############################
    # protocol PurePath methods #
    #############################

    def __hash__(self) -> int:
        """Protocol implementers are hashable."""
        ...

    # comparison methods
    def __lt__(self, other: Self) -> bool:
        """Comparison methods other than equality are only guaranteed for members of the same type.

        Specifically, :class:`ContainerPath` objects are not comparable to other types of objects.
        For sorting, consider using :func:`str` or :func:`repr` as the key.
        """
        ...

    def __le__(self, other: Self) -> bool:
        """Comparison methods other than equality are only guaranteed for members of the same type.

        Specifically, :class:`ContainerPath` objects are not comparable to other types of objects.
        For sorting, consider using :func:`str` or :func:`repr` as the key.
        """
        ...

    def __gt__(self, other: Self) -> bool:
        """Comparison methods other than equality are only guaranteed for members of the same type.

        Specifically, :class:`ContainerPath` objects are not comparable to other types of objects.
        For sorting, consider using :func:`str` or :func:`repr` as the key.
        """
        ...

    def __ge__(self, other: Self) -> bool:
        """Comparison methods other than equality are only guaranteed for members of the same type.

        Specifically, :class:`ContainerPath` objects are not comparable to other types of objects.
        For sorting, consider using :func:`str` or :func:`repr` as the key.
        """
        ...

    def __eq__(self, other: object, /) -> bool:
        """Like all objects, equality testing is supported.

        However, :class:`ContainerPath` objects will compare inequal with all local filesystem
        paths, and even all paths in different containers.
        """
        ...

    def __truediv__(self, key: StrPathLike) -> Self:
        """Return a new instance of the same type, with the other operand appended to its path.

        Used as ``protocol_implementor / str_or_pathlike``.

        .. note::
            ``__rtruediv__`` is currently not part of this protocol, as
            :class:`ContainerPath` objects only support absolute paths.
        """
        ...

    def __str__(self) -> str:
        """Return the string representation of the path.

        Exactly like :class:`pathlib.Path` for local paths. Following this convention,
        remote filesystem paths like :class:`ContainerPath` return the string representation
        of the path in the remote filesystem. The string representation is suitable for
        use with system calls (on the correct local or remote system) and Pebble layers.
        """
        ...

    def as_posix(self) -> str:
        """Return the string representation of the path with.

        Identical to :meth:`__str__`, since we only support posix systems.
        """
        ...

    def is_absolute(self) -> bool:
        """Return True if the path is absolute (has a root).

        .. note::
            Currently always ``True`` for :class:`ContainerPath`.
        """
        ...

    def match(self, path_pattern: str) -> bool:
        """Return true if this path matches the given pattern.

        If the pattern is relative, matching is done from the right; otherwise, the entire
        path is matched. The recursive wildcard ``'**'`` is **not** supported by this method.

        .. warning::
            Python 3.12's :class:`pathlib.Path` adds the ``case_sensitive`` keyword argument
            (default False), which is not part of this protocol. The default behaviour is always
            case-insensitive matching.

        .. note::
            :class:`ContainerPath` only matches against its path, the container is not considered.
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

    def joinpath(self, *other: StrPathLike) -> Self:
        """Return a new instance of the same type, with its path joined with the arguments.

        Args:
            other: One or more :class:`str` or :class:`os.PathLike` objects.

        Returns: A new instance of the same type, updated as follows. For each item in other,
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
        """The path name's last suffix (if any) including leading ``'.'``, or an empty string."""
        ...

    @property
    def suffixes(self) -> list[str]:
        r"""A list of the path name's suffixes (if any), including leading ``'.'``\s."""
        ...

    @property
    def stem(self) -> str:
        """The path name, minus its last suffix: name == stem + suffix."""
        ...

    #########################
    # protocol Path methods #
    #########################

    def read_text(self) -> str:
        """Read the corresponding local or remote filesystem path and return the string contents.

        .. note::
            Compared to :meth:`pathlib.Path.write_text`, this method drops the ``encoding`` and
            ``errors`` args to simplify the API. The Python 3.13+ ``newline`` argument is also not
            required by this protocol.

        Returns: The utf-8 decoded contents of the file as a :class:`str`.

        Raises:
            FileNotFoundError: If this path does not exist.
            PebbleConnectionError: If the remote container cannot be reached.
            PermissionError: If the local or remote user does not have read permissions.
            UnicodeError: If the file's contents are not valid utf-8.
        """
        ...

    def read_bytes(self) -> bytes:
        """Read the corresponding local or remote filesystem path and return the binary contents.

        Returns: The file's raw contents as :class:`bytes`.

        Raises:
            FileNotFoundError: If this path does not exist.
            PebbleConnectionError: If the remote container cannot be reached.
            PermissionError: If the local or remote user does not have read permissions.
        """
        ...

    def iterdir(self) -> Generator[Self]:
        """Yield objects of the same type corresponding to the directory's contents.

        There are no guarantees about the order of the children. The special entries
        ``'.'`` and ``'..'`` are not included.

        Raises:
            FileNotFoundError: If this path does not exist.
            NotADirectoryError: If this path is not a directory.
            PebbleConnectionError: If the remote container cannot be reached.
            PermissionError: If the local or remote user does not have appropriate permissions.
        """
        ...

    def glob(self, pattern: str) -> Generator[Self]:
        r"""Iterate over this directory and yield all paths matching the provided pattern.

        For example, ``path.glob('*.txt')``, ``path.glob('*/foo.txt')``.

        .. warning::
            Recursive matching, using the ``'**'`` pattern, is not supported by
            :meth:`ContainerPath.glob`.

        Args:
            pattern: The string pattern to match against. It must be a relative pattern, that is
                it cannot begin with ``'/'``.

        Returns:
            A generator yielding objects of the same type as this path, corresponding to those
            of its children which match the pattern. If this path is not a directory, there will
            be no matches.

        Raises:
            FileNotFoundError: If this path does not exist.
            NotImplementedError: If pattern is an absolute path, or (in the case of
                :class:`ContainerPath`) if it uses the ``'**'`` pattern.
            PebbleConnectionError: If the remote container cannot be reached.
            PermissionError: If the local or remote user does not have appropriate permissions.
            ValueError: If the pattern is invalid.

        .. note::
            In Python 3.13, :meth:`pathlib.Path.glob` added support for ``pattern`` to be an
            :class:`os.PathLike`\[:class:`str`] instead of just a :class:`str`. This is not
            required by this protocol.

            The ``case_sensitive`` argument, added in Python 3.12, is also not required -- the
            default behaviour is case-insensitive matching.

            The ``recurse_symlinks`` argument, added in Python 3.13, is also not required,
            and is not supported by :meth:`ContainerPath.glob`, which does not support recursive
            matching.
        """
        ...

    def owner(self) -> str:
        """Return the user name of the file owner."""
        ...

    def group(self) -> str:
        """Return the group name of the file."""
        ...

    def exists(self) -> bool:
        """Whether this path exists.

        Will follow symlinks to determine if the symlink target exists. This means that exists
        will return False for a broken symlink.

        .. note::
            In Python 3.12, :class:`pathlib.Path.exists` added the ``follow_symlinks`` argument,
            defaulting to ``True``. This is not required by this protocol, and is unsupported by
            :class:`ContainerPath.exists` due to current Pebble limitations.
        """
        ...

    def is_dir(self) -> bool:
        """Whether this path exists and is a directory.

        Will follow symlinks to determine if the symlink target exists and is a directory.

        .. note::
            In Python 3.13, :class:`pathlib.Path.is_dir` added the ``follow_symlinks`` argument,
            defaulting to ``True``. This is not required by this protocol, and is unsupported by
            :class:`ContainerPath.is_dir` due to current Pebble limitations.
        """
        ...


    def is_file(self) -> bool:
        """Whether this path exists and is a regular file.

        Will follow symlinks to determine if the symlink target exists and is a regular file.

        .. note::
            In Python 3.13, :class:`pathlib.Path.is_file` added the ``follow_symlinks`` argument,
            defaulting to ``True``. This is not required by this protocol, and is unsupported by
            :class:`ContainerPath.is_file` due to current Pebble limitations.
        """
        ...

    def is_fifo(self) -> bool:
        """Whether this path exists and is a named pipe (aka FIFO).

        Will follow symlinks to determine if the symlink target exists and is a named pipe.
        """
        ...

    def is_socket(self) -> bool:
        """Whether this path exists and is a socket.

        Will follow symlinks to determine if the symlink target exists and is a socket.
        """
        ...

    ##################################################
    # protocol Path methods with extended signatures #
    ##################################################

    def write_bytes(
        self,
        data: bytes,
        *,
        mode: int = _constants.DEFAULT_WRITE_MODE,
        user: str | None = None,
        group: str | None = None,
    ) -> int: ...

    def write_text(
        self,
        data: str,
        # # we drop encoding and errors for a simpler API
        # # TODO: move this information to the docstring
        # encoding: str | None = None,
        # errors: typing.Literal['strict', 'ignore'] | None = None,
        # # newline is not part of the protocol since we support Python 3.8+
        # newline: typing.Literal['', '\n', '\r', '\r\n'] | None = None,  # 3.10+
        *,
        mode: int = _constants.DEFAULT_WRITE_MODE,
        user: str | None = None,
        group: str | None = None,
    ) -> int: ...

    # make_dir
    def mkdir(
        self,
        mode: int = _constants.DEFAULT_MKDIR_MODE,
        parents: bool = False,
        exist_ok: bool = False,
        *,
        user: str | None = None,
        group: str | None = None,
    ) -> None: ...


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

# def __rtruediv__(self, key: StrPathLike) -> Self: ...
# omitted from v1 protocol
# doesn't seem worth supporting until (if) ContainerPath gets relative paths
#
# when we have relative paths, it will be meaningful to support the following:
# def __truediv__(self, key: StrPathLike | Self) -> Self: ...
# def __rtruediv__(self, key: StrPathLike | Self) -> Self: ...
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

# remove
# these methods are problematic because Pebble
# 1. doesn't let us distinguish in advance between dirs and symlinks to them
# 2. doesn't provide a way not to remove an empty directory
#
# If provided, would have to also remove symlinks to directories
# def rmdir(self) -> None: ...
#
# If provided, would either have to also remove empty directories
# or be unable to remove symlinks to directories
# def unlink(self, missing_ok: bool = False) -> None: ...

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

# def is_symlink(self) -> bool: ...
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
