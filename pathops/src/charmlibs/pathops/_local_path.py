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

"""Implementation of LocalPath class."""

from __future__ import annotations

import grp
import os
import pathlib
import pwd
import shutil
import typing

from . import _constants

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Buffer, Self


class LocalPath(pathlib.PosixPath):
    r""":class:`pathlib.PosixPath` subclass with extended file-creation method arguments.

    .. note::
        The :meth:`write_bytes`, :meth:`write_text`, and :meth:`mkdir` methods are extended with
        file permission and ownership arguments, for compatibility with :class:`PathProtocol`.

    Args:
        \*parts: :class:`str` or :class:`os.PathLike`. ``LocalPath`` takes no keyword arguments.

    ::

        LocalPath(pathlib.Path('/foo'))
        LocalPath('/', 'foo')
    """

    def write_bytes(
        self,
        data: Buffer,
        *,
        mode: int | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> int:
        """Write the provided data to the corresponding local filesystem path.

        Compared to :meth:`pathlib.Path.write_bytes`, this method adds ``mode``, ``user``
        and ``group`` args. These are used to set the permissions and ownership of the file.

        Args:
            data: The bytes to write, typically a :class:`bytes` object, but may also be a
                :class:`bytearray` or :class:`memoryview`.
            mode: The permissions to set on the file. Defaults to 0o644 (-rw-r--r--) for new files.
                If the file already exists, its permissions will be changed, using
                :meth:`pathlib.PosixPath.chmod`, unless ``mode`` is ``None`` (default).
            user: The name of the user to set for the file using :func:`shutil.chown`.
                Validated to be an existing user before writing.
                If the file already exists, its user and group will be changed,
                unless ``user`` is ``None`` (default).
            group: The name of the group to set for the file using :func:`shutil.chown`.
                Validated to be an existing group before writing.
                If the file already exists, its group will be changed,
                unless ``user`` and ``group`` are ``None`` (default).

        Returns:
            The number of bytes written.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            LookupError: if the user or group is unknown.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the local user does not have permissions for the operation.
        """
        _validate_user_and_group(user=user, group=group)
        with self._open_for_write(mode=mode, user=user, group=group, text=False) as f:
            return f.write(memoryview(data))

    def write_text(
        self,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
        *,
        mode: int | None = None,
        user: str | None = None,
        group: str | None = None,
    ) -> int:
        r"""Write the provided string to the corresponding local filesystem path.

        Compared to :meth:`pathlib.Path.write_bytes`, this method adds ``mode``, ``user``
        and ``group`` args. These are used to set the permissions and ownership of the file.

        .. warning::
            :class:`ContainerPath` and :class:`PathProtocol` do not support the ``encoding``,
            ``errors``, and ``newline`` arguments of :meth:`pathlib.Path.write_text`.
            For :class:`ContainerPath` compatible code, do not use these arguments.
            They are provided to allow :class:`LocalPath` to be used as a drop-in
            replacement for :class:`pathlib.Path` if needed.

        Args:
            data: The string to write. Newlines are not modified on writing.
            encoding: The encoding to use when writing the data, defaults to 'UTF-8'.
            errors: 'strict' to raise any encoding errors, 'ignore' to ignore them.
                Defaults to 'strict'.
            newline: If ``None``, ``''``, or ``'\n'``, then '\n' will be written as is.
                This is the default behaviour. If ``newline`` is ``'\r'`` or ``'\r\n'``,
                then ``'\n'`` will be replaced with ``newline`` in memory before writing.
            mode: The permissions to set on the file. Defaults to 0o644 (-rw-r--r--) for new files.
                If the file already exists, its permissions will be changed, using
                :meth:`pathlib.PosixPath.chmod`, unless ``mode`` is ``None`` (default).
            user: The name of the user to set for the file using :func:`shutil.chown`.
                Validated to be an existing user before writing.
                If the file already exists, its user and group will be changed,
                unless ``user`` is ``None`` (default).
            group: The name of the group to set for the file using :func:`shutil.chown`.
                Validated to be an existing group before writing.
                If the file already exists, its group will be changed,
                unless ``user`` and ``group`` are ``None`` (default).

        Returns:
            The number of bytes written.

        Raises:
            FileNotFoundError: if the parent directory does not exist.
            LookupError: if the user or group is unknown.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the local user does not have permissions for the operation.
            ValueError: if ``newline`` is any value other than those documented above.
        """
        _validate_user_and_group(user=user, group=group)
        if newline in ('\r', '\r\n'):
            data = data.replace('\n', newline)
        elif newline not in ('', '\n', None):
            raise ValueError(f'illegal newline value: {newline!r}')
        with self._open_for_write(
            mode=mode, user=user, group=group, text=True, encoding=encoding, errors=errors
        ) as f:
            return f.write(data)

    def _open_for_write(
        self,
        *,
        mode: int | None,
        user: str | None,
        group: str | None,
        text: bool,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> typing.IO[typing.Any]:
        # Set the permissions and ownership on the open file descriptor before any content is
        # written, so that the content is never readable with the wrong permissions or owner.
        # Because the descriptor is already open, this also works when the requested mode is
        # not writable (for example, 0o444) and the local user is not root.
        # A new file is created private if the caller specified a mode (the umask only ever
        # removes permissions), or with Pebble's default write mode otherwise.
        create_mode = _constants.DEFAULT_WRITE_MODE if mode is None else 0o600
        fd = os.open(self, os.O_WRONLY | os.O_CREAT, create_mode)
        try:
            _fchown_if_needed(fd, user=user, group=group)
            if mode is not None:
                # explicitly set the mode if the user requested it
                os.fchmod(fd, mode)
            os.ftruncate(fd, 0)
            if text:
                # newline='' because newlines were already handled by the caller.
                return open(fd, 'w', encoding=encoding, errors=errors, newline='')
            return open(fd, 'wb')
        except BaseException:
            os.close(fd)
            raise

    def glob(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, pattern: str | os.PathLike[str]
    ) -> Iterator[Self]:
        # On Python 3.12 and earlier, pathlib.Path.glob only accepts a str pattern.
        # ContainerPath.glob accepts str | os.PathLike[str], so we normalise here to match.
        return super().glob(os.fspath(pattern))

    def mkdir(
        self,
        mode: int = _constants.DEFAULT_MKDIR_MODE,
        parents: bool = False,
        exist_ok: bool = False,
        *,
        user: str | None = None,
        group: str | None = None,
    ) -> None:
        """Create a new directory at the corresponding local filesystem path.

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
            user: The name of the user to set for the directory using :func:`shutil.chown`.
                Validated to be an existing user before writing.
                The user and group are not changed if the directory already exists.
            group: The name of the group to set for the directory using :func:`shutil.chown`.
                Validated to be an existing group before writing.
                The user and group are not changed if the directory already exists.

        Raises:
            FileExistsError: if the directory already exists and ``exist_ok`` is ``False``.
            FileNotFoundError: if the parent directory does not exist and ``parents`` is ``False``.
            LookupError: if the user or group is unknown.
            NotADirectoryError: if the parent exists as a non-directory file.
            PermissionError: if the local user does not have permissions for the operation.
        """
        _validate_user_and_group(user=user, group=group)
        already_exists = self.exists()
        super().mkdir(mode=mode, parents=parents, exist_ok=exist_ok)
        if not already_exists:
            _chown_if_needed(self, user=user, group=group)


def _validate_user_and_group(user: str | None, group: str | None):
    if user is not None:
        pwd.getpwnam(user)
    if group is not None:
        grp.getgrnam(group)


def _fchown_if_needed(fd: int, user: str | None, group: str | None) -> None:
    if user is None and group is None:
        return
    uid = -1
    gid = -1
    if user is not None:
        info = pwd.getpwnam(user)
        uid = info.pw_uid
        gid = info.pw_gid  # use the user's group, following Pebble
    if group is not None:
        gid = grp.getgrnam(group).gr_gid
    os.fchown(fd, uid, gid)


def _chown_if_needed(path: pathlib.Path, user: str | int | None, group: str | int | None) -> None:
    if user is not None:
        if group is None:  # use the user's group, following Pebble
            info = pwd.getpwnam(user) if isinstance(user, str) else pwd.getpwuid(user)
            group = info.pw_gid
        shutil.chown(path, user=user, group=group)
    elif group is not None:
        shutil.chown(path, group=group)
