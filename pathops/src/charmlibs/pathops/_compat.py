# Copyright 2026 Canonical Ltd.
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

"""Polyfills for pathlib methods added in newer Python versions."""

from __future__ import annotations

import functools
import pathlib
import re

_SEP = '/'


def full_match(path: str, pattern: str, *, case_sensitive: bool | None = None) -> bool:
    """Polyfill for pathlib.PurePath.full_match (Python 3.13+).

    Matches ``str(PurePosixPath(path))`` against a regex built from
    ``str(PurePosixPath(pattern))``, mirroring pathlib's regex-based semantics
    with ``recursive=True, include_hidden=True``. ``**`` matches zero or more
    path components.

    ``case_sensitive`` mirrors pathlib's parameter: ``None`` (the default) uses
    the OS default (case-sensitive on POSIX), ``True`` forces case-sensitive,
    and ``False`` forces case-insensitive matching.
    """
    return (
        _compile(pattern, case_sensitive is False).match(str(pathlib.PurePosixPath(path)))
        is not None
    )


@functools.lru_cache(maxsize=256)
def _compile(pattern: str, ignore_case: bool) -> re.Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(_translate(str(pathlib.PurePosixPath(pattern))), flags)


def _translate(pattern: str) -> str:
    """Translate a glob-style pattern to a regex.

    Ported from ``glob.translate`` (added in Python 3.13), specialised to
    ``recursive=True, include_hidden=True`` with a single POSIX separator.
    """
    sep = re.escape(_SEP)
    not_sep = f'[^{sep}]'
    one_last_segment = f'{not_sep}+'
    one_segment = f'{one_last_segment}{sep}'
    any_segments = f'(?:.+{sep})?'
    any_last_segments = '.*'

    parts = pattern.split(_SEP)
    last = len(parts) - 1
    out: list[str] = []
    for i, part in enumerate(parts):
        if part == '*':
            out.append(one_segment if i < last else one_last_segment)
        elif part == '**':
            if i < last:
                if parts[i + 1] != '**':
                    out.append(any_segments)
            else:
                out.append(any_last_segments)
        else:
            if part:
                out.extend(_translate_segment(part, star=f'{not_sep}*', question=not_sep))
            if i < last:
                out.append(sep)
    return rf'(?s:{"".join(out)})\Z'


def _translate_segment(pattern: str, *, star: str, question: str) -> list[str]:
    """Translate a single glob segment. Ported from CPython's ``fnmatch._translate``."""
    res: list[str] = []
    add = res.append
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        i = i + 1
        if c == '*':
            if (not res) or res[-1] is not star:
                add(star)
        elif c == '?':
            add(question)
        elif c == '[':
            j = i
            if j < n and pattern[j] == '!':
                j = j + 1
            if j < n and pattern[j] == ']':
                j = j + 1
            while j < n and pattern[j] != ']':
                j = j + 1
            if j >= n:
                add(r'\[')
            else:
                stuff = pattern[i:j]
                if '-' not in stuff:
                    stuff = stuff.replace('\\', r'\\')
                else:
                    chunks: list[str] = []
                    k = i + 2 if pattern[i] == '!' else i + 1
                    while True:
                        k = pattern.find('-', k, j)
                        if k < 0:
                            break
                        chunks.append(pattern[i:k])
                        i = k + 1
                        k = k + 3
                    chunk = pattern[i:j]
                    if chunk:
                        chunks.append(chunk)
                    else:
                        chunks[-1] += '-'
                    for k in range(len(chunks) - 1, 0, -1):
                        if chunks[k - 1][-1] > chunks[k][0]:
                            chunks[k - 1] = chunks[k - 1][:-1] + chunks[k][1:]
                            del chunks[k]
                    stuff = '-'.join(s.replace('\\', r'\\').replace('-', r'\-') for s in chunks)
                stuff = re.sub(r'([&~|])', r'\\\1', stuff)
                i = j + 1
                if not stuff:
                    add('(?!)')
                elif stuff == '!':
                    add('.')
                else:
                    if stuff[0] == '!':
                        stuff = '^' + stuff[1:]
                    elif stuff[0] in ('^', '['):
                        stuff = '\\' + stuff
                    add(f'[{stuff}]')
        else:
            add(re.escape(c))
    return res
