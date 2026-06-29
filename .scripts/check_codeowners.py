#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

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

"""Validate the repository's CODEOWNERS file.

Two checks are performed:

1. Every package and interface directory has an explicit code owner, rather than
   falling back to the repository maintainers via the catch-all `*` entry.
2. Every path-based CODEOWNERS entry corresponds to a real path in the repository,
   so renaming or removing a directory can't leave behind an orphan entry.

Exit with success (0) if both checks pass, otherwise print the problems to stdout
and exit with failure (the number of problems found).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

# `.scripts/check_codeowners.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CODEOWNERS = REPO_ROOT / 'CODEOWNERS'
LS = pathlib.Path(__file__).resolve().parent / 'ls.py'


def main() -> int:
    """Run both CODEOWNERS checks, printing any problems and returning the problem count."""
    entries = parse_codeowners(CODEOWNERS.read_text())
    directories = [*_ls('packages'), *_ls('interfaces')]
    problems = 0
    for directory in find_unowned_dirs(directories, entries):
        print(f'No explicit CODEOWNERS entry for: /{directory}/')
        problems += 1
    for pattern in find_orphan_entries(entries, REPO_ROOT):
        print(f'CODEOWNERS entry points at a missing path: {pattern}')
        problems += 1
    if problems == 0:
        print('All packages and interfaces have a CODEOWNERS entry, and no entries are orphaned.')
    return problems


class Entry(typing.NamedTuple):
    """A single CODEOWNERS entry: a path pattern and its owners."""

    pattern: str
    owners: tuple[str, ...]


def parse_codeowners(text: str) -> list[Entry]:
    """Parse CODEOWNERS file contents into a list of `Entry`s, ignoring comments and blanks."""
    entries: list[Entry] = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        entries.append(Entry(pattern=pattern, owners=tuple(owners)))
    return entries


def _ls(category: str) -> list[str]:
    """Return the repo-relative paths of all `packages` or `interfaces`, excluding testing.

    Example and namespace-placeholder directories are included: they exist in the repo
    long-term, so they get an explicit CODEOWNERS entry like any other directory. Testing
    packages are excluded, as they're always children of an existing library and so are
    already covered by that library's entry.
    """
    cmd = [str(LS), category, '--exclude-testing']
    return json.loads(subprocess.check_output(cmd))


def find_unowned_dirs(directories: Iterable[str], entries: Iterable[Entry]) -> list[str]:
    """Return directories without an explicit (non catch-all) CODEOWNERS entry with an owner.

    A directory is considered explicitly owned if some entry with at least one owner points
    at the directory itself or at a path inside it. This covers both whole-directory entries
    (e.g. `/apt/`) and split entries (e.g. `/interfaces/foo/interface/` plus
    `/interfaces/foo/ruff.toml`), without treating the catch-all `*` fallback as ownership.
    """
    owned_targets = [
        target
        for entry in entries
        if entry.owners
        if (target := entry_target(entry.pattern)) is not None
    ]
    unowned: list[str] = []
    for directory in directories:
        dir_path = pathlib.PurePosixPath(directory.strip('/'))
        if not any(target == dir_path or dir_path in target.parents for target in owned_targets):
            unowned.append(directory)
    return unowned


def find_orphan_entries(entries: Iterable[Entry], root: pathlib.Path) -> list[str]:
    """Return the patterns of path-based entries that don't point at an existing path."""
    orphans: list[str] = []
    for entry in entries:
        target = entry_target(entry.pattern)
        if target is None:
            continue
        if not (root / target).exists():
            orphans.append(entry.pattern)
    return orphans


def entry_target(pattern: str) -> pathlib.PurePosixPath | None:
    """Return the repo-relative path that an anchored CODEOWNERS path pattern points to.

    Returns `None` for non-path patterns (those containing glob wildcards, or the
    catch-all `*`), which aren't validated as real paths.
    """
    if any(char in pattern for char in '*?[]'):
        return None
    # CODEOWNERS paths are anchored to the repo root with a leading slash, and a
    # trailing slash just means "this is a directory"; neither affects the path.
    return pathlib.PurePosixPath(pattern.strip('/'))


if __name__ == '__main__':
    sys.exit(main())
