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

"""Methods for matching Python Exceptions to Pebble Errors and creating Exception objects."""

from __future__ import annotations

import errno
import os
from typing import NoReturn

from ops import pebble


def raise_if_matches_directory_not_empty(error: pebble.Error, msg: str) -> None:
    if (
        isinstance(error, pebble.PathError)
        and error.kind == 'generic-file-error'
        and 'directory not empty' in error.message
    ):
        raise OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), msg) from error


def raise_file_exists(msg: str, from_: BaseException | None = None) -> NoReturn:
    e = FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), msg)
    raise e from from_


def matches_file_exists(error: pebble.Error) -> bool:
    return (
        isinstance(error, pebble.PathError)
        and error.kind == 'generic-file-error'
        and 'file exists' in error.message
    )


def raise_if_matches_file_exists(error: pebble.Error, msg: str) -> None:
    if matches_file_exists(error):
        raise_file_exists(msg, from_=error)


def raise_file_not_found(msg: str, from_: BaseException | None = None) -> NoReturn:
    # pebble will return this error when trying to read_{text,bytes} a socket
    # pathlib raises OSError(errno.ENXIO, os.strerror(errno.ENXIO), path) in this case
    # displaying as "OSError: [Errno 6] No such device or address: '/path'"
    # since FileNotFoundError is a subtype of OSError, and this case should be rare
    # it seems sensible to just raise FileNotFoundError here, without checking
    # if the file in question is a socket
    raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), msg) from from_


def raise_if_matches_file_not_found(error: pebble.Error, msg: str) -> None:
    if (isinstance(error, pebble.APIError) and error.code == 404) or (
        isinstance(error, pebble.PathError) and error.kind == 'not-found'
    ):
        raise_file_not_found(msg, from_=error)


def raise_is_a_directory(msg: str, from_: BaseException | None = None) -> None:
    raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), msg) from from_


def raise_if_matches_is_a_directory(error: pebble.Error, msg: str) -> None:
    if (
        isinstance(error, pebble.PathError)
        and error.kind == 'generic-file-error'
        and 'can only read a regular file' in error.message
    ):
        raise_is_a_directory(msg, from_=error)


def raise_if_matches_lookup(error: pebble.Error, msg: str) -> None:
    if (
        isinstance(error, pebble.PathError)
        and error.kind == 'generic-file-error'
        and 'cannot look up user and group' in error.message
    ):
        raise LookupError(msg) from error


def matches_not_a_directory(error: pebble.Error) -> bool:
    return (
        isinstance(error, pebble.APIError)
        and error.code == 400
        and 'not a directory' in error.message
    ) or (
        isinstance(error, pebble.PathError)
        and error.kind == 'generic-file-error'
        and 'not a directory' in error.message
    )


def raise_not_a_directory(msg: str, from_: BaseException | None = None) -> NoReturn:
    raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), msg) from from_


def raise_if_matches_not_a_directory(error: pebble.Error, msg: str) -> None:
    if matches_not_a_directory(error):
        raise_not_a_directory(msg, from_=error)


def raise_if_matches_permission(error: pebble.Error, msg: str) -> None:
    if isinstance(error, pebble.PathError) and error.kind == 'permission-denied':
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), msg) from error


def raise_if_matches_too_many_levels_of_symlinks(error: pebble.Error, msg: str) -> None:
    if (
        (isinstance(error, pebble.APIError) and error.code == 400)
        or (isinstance(error, pebble.PathError) and error.kind == 'generic-file-error')
    ) and 'too many levels of symbolic links' in error.message:
        raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), msg) from error
