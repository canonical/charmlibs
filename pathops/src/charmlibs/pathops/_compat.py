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

import fnmatch
import pathlib


def full_match(path_str: str, pattern_str: str) -> bool:
    """Polyfill for pathlib.PurePath.full_match (Python 3.13+).

    Unlike PurePath.match, always anchors the pattern against the entire path.
    Relative patterns are anchored to the filesystem root.
    Supports ``**`` wildcards that match zero or more path components.
    """
    if not pattern_str:
        raise ValueError('empty pattern')
    pat = pathlib.PurePosixPath(pattern_str)
    path = pathlib.PurePosixPath(path_str)
    pat_parts = pat.parts if pat.is_absolute() else ('/', *pat.parts)
    return _match_parts(path.parts, pat_parts)


def _match_parts(path_parts: tuple[str, ...], pat_parts: tuple[str, ...]) -> bool:
    if not pat_parts:
        return not path_parts
    if not path_parts:
        # Remaining pattern matches only if it consists entirely of **
        return all(p == '**' for p in pat_parts)
    first = pat_parts[0]
    if first == '**':
        rest = pat_parts[1:]
        # ** matches zero or more path components
        return any(_match_parts(path_parts[i:], rest) for i in range(len(path_parts) + 1))
    if not fnmatch.fnmatchcase(path_parts[0], first):
        return False
    return _match_parts(path_parts[1:], pat_parts[1:])
