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

"""Public helper functions exported by this package."""

from __future__ import annotations

import pathlib
import re
import typing

from . import _constants, _fileinfo
from ._container_path import ContainerPath
from ._local_path import LocalPath

if typing.TYPE_CHECKING:
    import os
    from typing import BinaryIO, Literal, TextIO

    from ops import pebble
    from typing_extensions import TypeIs

    from ._types import PathProtocol


def ensure_contents(
    path: str | os.PathLike[str] | PathProtocol,
    source: bytes | str | BinaryIO | TextIO,
    *,
    matcher: str | re.Pattern[str] | None = None,
    no_match: Literal['ignore', 'append', 'replace'] = 'ignore',
    mode: int = _constants.DEFAULT_WRITE_MODE,
    user: str | None = None,
    group: str | None = None,
) -> bool:
    r"""Ensure ``source`` can be read from ``path``. Return True if any changes were made.

    Ensure that ``path`` exists, contains ``source``, has the correct permissions (``mode``),
    and has the correct file ownership (``user`` and ``group``).

    If ``matcher`` is provided, ``source`` is instead the replacement text: every
    substring matching ``matcher`` is replaced by ``source``. If the file doesn't
    match, ``no_match`` decides what happens; if the file doesn't exist, ``source``
    is written. In this mode the file is read and written as UTF-8 text, and
    ``source`` must not end with a newline: the matched line's newline is preserved
    automatically, and a ``source`` written whole (file creation, append, replace)
    is newline-terminated automatically.

    Args:
        path: A local or remote filesystem path.
        source: The desired contents in ``str`` or ``bytes`` form, or an object with a ``.read()``
            method which returns a ``str`` or ``bytes`` object.
        matcher: A regular expression to search for in the file's current contents.
            A ``str`` is compiled with :const:`re.MULTILINE`, so ``^`` and ``$`` match at
            line boundaries. For any other flags -- for example a pattern that spans
            multiple lines -- pass a precompiled :class:`re.Pattern` instead, which is
            used as-is with its own flags.
        no_match: What to do if ``matcher`` is provided but the file doesn't match:
            ``'ignore'`` (default) to leave the file unchanged, ``'append'`` to append
            ``source`` to the file, or ``'replace'`` to write the file with ``source``.
            Ignored if the file doesn't exist, in which case ``source`` is written.
        mode: The desired file permissions.
        user: The desired file owner, or ``None`` to not change the owner.
        group: The desired group, or ``None`` to not change the group.

    Returns:
        ``True`` if any changes were made, including permissions or ownership, otherwise ``False``.

    Raises:
        LookupError: if the user or group is unknown.
        NotADirectoryError: if the parent exists as a non-directory file.
        PermissionError: if the user does not have permissions for the operation.
        ValueError: if ``matcher`` is provided and ``source`` ends with a newline
            (literal or ``\n`` escape); or if ``no_match`` is ``'append'`` or
            ``'replace'``, the file doesn't match, and ``source`` contains
            backreferences (there is no match to expand them against).
        UnicodeDecodeError: if ``matcher`` is provided and the file's contents are not
            valid UTF-8.
        :class:`PebbleConnectionError`: if the remote Pebble client cannot be reached.
    """
    if _is_str_pathlike(path):
        path = LocalPath(path)
    if matcher is not None:
        if not isinstance(matcher, re.Pattern):
            matcher = re.compile(matcher, re.MULTILINE)
        template = _as_text(source)
        if template.endswith(('\n', '\\n')):
            raise ValueError(
                'in matcher mode, source must not end with a newline: '
                "the matched line's newline is preserved automatically"
            )
        # a source written whole is a single newline-terminated line
        source_bytes = template.encode() + b'\n'
    else:
        source_bytes = _as_bytes(source)
        template = None
    try:
        info = _get_fileinfo(path)
    except FileNotFoundError:
        current = None  # file doesn't exist, so writing is required
    else:
        current = path.read_bytes()
        if (
            (info.permissions == mode)
            and (user is None or info.user == user)
            and (group is None or info.group == group)
            and _contents_match(current, source_bytes, matcher, template, no_match)
        ):
            return False  # everything matches, so writing is not required
    path.parent.mkdir(parents=True, exist_ok=True)
    if current is None:
        desired = source_bytes
    elif matcher is not None and template is not None:
        desired = _edit_contents(current, source_bytes, matcher, template, no_match)
    else:
        desired = source_bytes
    path.write_bytes(desired, mode=mode, user=user, group=group)
    return True


def _edit_contents(
    current: bytes,
    source: bytes,
    matcher: re.Pattern[str],
    template: str,
    no_match: Literal['ignore', 'append', 'replace'],
) -> bytes:
    """The desired contents, given the file's current contents and a matcher."""
    current_text = current.decode()
    if matcher.search(current_text):
        return matcher.sub(template, current_text).encode()
    if no_match == 'ignore':
        return current
    if re.search(r'\\[1-9]|\\g<', template):
        raise ValueError('source contains backreferences but the file has no match')
    if no_match == 'append':
        # newline-terminate the file so the appended line is its own line
        return current.removesuffix(b'\n') + b'\n' + source
    return source


def _contents_match(
    current: bytes,
    source: bytes,
    matcher: re.Pattern[str] | None,
    template: str | None,
    no_match: Literal['ignore', 'append', 'replace'],
) -> bool:
    """Whether the file's current contents already match the desired contents."""
    if matcher is None or template is None:
        return current == source
    current_text = current.decode()
    if not matcher.search(current_text):
        # no match: the desired contents are source appended, or the file unchanged
        return current + source == current if no_match == 'append' else no_match == 'ignore'
    return matcher.sub(template, current_text).encode() == current


def _as_text(source: str | bytes | BinaryIO | TextIO) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, bytes):
        return source.decode()
    return _as_text(source.read())


def _is_str_pathlike(obj: object) -> TypeIs[str | os.PathLike[str]]:
    return isinstance(obj, str) or hasattr(obj, '__fspath__')


def _get_fileinfo(
    path: str | os.PathLike[str] | PathProtocol, follow_symlinks: bool = True
) -> pebble.FileInfo:
    if isinstance(path, ContainerPath):
        return _fileinfo.from_container_path(path, follow_symlinks=follow_symlinks)
    assert _is_str_pathlike(path)
    return _fileinfo.from_pathlib_path(pathlib.Path(path), follow_symlinks=follow_symlinks)


def _as_bytes(source: bytes | str | BinaryIO | TextIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        return source.encode()
    return _as_bytes(source.read())
