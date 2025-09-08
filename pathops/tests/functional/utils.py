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

"""Constants and helpers for use in conftest.py and tests."""

from __future__ import annotations

import pathlib
import socket
import string
import tempfile
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from ops import pebble

########################
# session_dir contents #
########################

BINARY_FILE_NAME = 'binary_file.bin'
BROKEN_SYMLINK_NAME = 'symlink_broken'
EMPTY_DIR_NAME = 'empty_dir'
EMPTY_DIR_SYMLINK_NAME = 'symlink_dir'
EMPTY_FILE_NAME = 'empty_file.bin'
FILE_SYMLINK_NAME = 'symlink.bin'
MISSING_FILE_NAME = 'does_not_exist'
NESTED_DIR_NAME = 'nested_dir'
NESTED_DIR_PATTERN = 'nested*dir'
NESTED_MATCH_NOT_A_DIR = 'nested-empty-file-not-a-dir'
OUROBOROS_SYMLINK_NAME = 'symlink_to_itself'
RECURSIVE_SYMLINK_NAME = 'symlink_rec'
SOCKET_NAME = 'socket.socket'
SOCKET_SYMLINK_NAME = 'symlink.socket'
TEXT_FILE_NAME = 'alphabet.txt'

TEXT_FILES: Mapping[str, str] = {
    TEXT_FILE_NAME: 'abcd\r\nefg\rhijk\nlmnop\r\nqrs\rtuv\nw\r\nx\ry\nz',
    'bar.txt': string.ascii_uppercase + string.ascii_lowercase,
    'baz.txt': '',
    'bartholemew.txt': 'Bartholemew',
}
UTF8_BINARY_FILES: Mapping[str, bytes] = {
    str(pathlib.Path(k).with_suffix('.utf-8')): v.encode() for k, v in TEXT_FILES.items()
}
UTF16_BINARY_FILES: Mapping[str, bytes] = {
    str(pathlib.Path(k).with_suffix('.utf-16')): v.encode('utf-16') for k, v in TEXT_FILES.items()
}
BINARY_FILES: Mapping[str, bytes | bytearray] = {
    BINARY_FILE_NAME: bytearray(range(256)),
    **UTF8_BINARY_FILES,
    **UTF16_BINARY_FILES,
}


def _populate_interesting_dir(main_dir: pathlib.Path) -> Callable[[], None]:
    nested_dir = main_dir / NESTED_DIR_NAME
    nested_dir.mkdir()
    doubly_nested_dir = nested_dir / NESTED_DIR_NAME
    doubly_nested_dir.mkdir()
    sockets: list[socket.socket] = []
    for directory in (main_dir, nested_dir, doubly_nested_dir):
        (directory / EMPTY_DIR_NAME).mkdir()
        empty_file = directory / EMPTY_FILE_NAME
        empty_file.touch()
        decoy_file = directory / NESTED_MATCH_NOT_A_DIR
        decoy_file.touch()
        (directory / FILE_SYMLINK_NAME).symlink_to(empty_file)
        (directory / EMPTY_DIR_SYMLINK_NAME).symlink_to(directory / EMPTY_DIR_NAME)
        (directory / RECURSIVE_SYMLINK_NAME).symlink_to(directory)
        (directory / BROKEN_SYMLINK_NAME).symlink_to(directory / MISSING_FILE_NAME)
        (directory / OUROBOROS_SYMLINK_NAME).symlink_to(directory / OUROBOROS_SYMLINK_NAME)
        for filename, contents in TEXT_FILES.items():
            (directory / filename).write_text(contents)
        for filename, contents in BINARY_FILES.items():
            (directory / filename).write_bytes(contents)
        sock = socket.socket(socket.AddressFamily.AF_UNIX)
        sock.bind(str(directory / SOCKET_NAME))
        sockets.append(sock)
        (directory / SOCKET_SYMLINK_NAME).symlink_to(directory / SOCKET_NAME)
        # TODO: make block device?
    assert not (main_dir / MISSING_FILE_NAME).exists()
    assert not (nested_dir / MISSING_FILE_NAME).exists()
    assert not (doubly_nested_dir / MISSING_FILE_NAME).exists()

    def cleanup() -> None:
        for s in sockets:
            s.shutdown(socket.SHUT_RDWR)
            s.close()

    return cleanup


def _make_session_dir() -> tuple[pathlib.Path, Callable[[], None]]:
    context_manager = tempfile.TemporaryDirectory()
    dirname = context_manager.__enter__()
    tempdir = pathlib.Path(dirname)
    cleanup = _populate_interesting_dir(tempdir)

    def teardown() -> None:
        cleanup()
        context_manager.__exit__(None, None, None)

    return tempdir, teardown


# The filenames are used to parametrize tests, so they need to be ready at test collection time.
# This means we need to generate the list *before* pytest does fixture creation.
# To avoid redundantly creating a second directory just to scrape the names from,
# we create the temporary directory here at import time, along with its teardown function.
# The session_dir fixture defined in conftest.py yields the path and calls the teardown function.
_SESSION_DIR_PATH, _TEARDOWN_SESSION_DIR = _make_session_dir()
FILENAMES = tuple(path.name for path in _SESSION_DIR_PATH.iterdir())
FILENAMES_PLUS = (*FILENAMES, MISSING_FILE_NAME, f'{MISSING_FILE_NAME}/{MISSING_FILE_NAME}')

#########
# utils #
#########


def info_to_dict(info: pebble.FileInfo, *, exclude: Sequence[str] | str = ()) -> dict[str, object]:
    if isinstance(exclude, str):
        exclude = (exclude,)
    names = dir(info)
    bad_excludes = tuple(name for name in exclude if name not in names)
    if bad_excludes:
        raise ValueError(
            f'exclude={exclude!r} but these are not FileInfo attributes: {bad_excludes!r}'
        )
    return {
        name: getattr(info, name)
        for name in names
        if (not name.startswith('_')) and (name != 'from_dict') and (name not in exclude)
    }
