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

Two checks are performed against every top-level path and every immediate child of `interfaces/`:

1. Each path is owned, meaning either the path itself has a CODEOWNERS entry with an owner, or
   (for a directory) every one of its immediate children is owned. This ensures ownership isn't
   left to fall through to the repository maintainers via the catch-all `*` entry, while still
   allowing a directory to be covered by per-child entries (such as an interface's `interface/`
   plus `ruff.toml`).
2. Every path-based CODEOWNERS entry corresponds to a real path in the repository, so renaming
   or removing a directory can't leave behind a bad entry.

Exit with success (0) if both checks pass, otherwise print the problems to stdout
and exit with failure (the number of problems found).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import typing

# `.scripts/check_codeowners.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CODEOWNERS = REPO_ROOT / 'CODEOWNERS'


ROOT = pathlib.PurePosixPath()  # the repository root, as a relative path


def main() -> int:
    """Run both CODEOWNERS checks, printing any problems and returning the problem count."""
    entries = parse_codeowners(CODEOWNERS.read_text())
    files = [pathlib.PurePosixPath(f) for f in tracked_files(REPO_ROOT)]
    problems = 0
    for path in find_unowned_dirs(entries, files):
        print(f'No explicit CODEOWNERS entry for: {render(path, files)}')
        problems += 1
    for entry in find_bad_entries(entries, REPO_ROOT):
        print(f'CODEOWNERS entry points at a missing path: {entry.pattern}')
        problems += 1
    if problems == 0:
        print('Every path has a CODEOWNERS owner, and no entries are bad.')
    return problems


class Entry(typing.NamedTuple):
    """A single CODEOWNERS entry: the raw `pattern` and its `owners`."""

    pattern: str
    owners: tuple[str, ...]


def parse_codeowners(text: str) -> dict[pathlib.PurePosixPath, Entry]:
    """Parse CODEOWNERS into a `{target: entry}` dict, keyed by the repo-relative path it covers.

    Comments, blanks, and wildcard patterns (containing any of `*?[]`, such as the catch-all `*`)
    are ignored: wildcards aren't anchored paths, so this check neither validates nor counts them.
    Keys are `PurePosixPath`s, so a trailing slash on a directory entry doesn't affect lookups.
    """
    entries: dict[pathlib.PurePosixPath, Entry] = {}
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        if any(char in pattern for char in '*?[]'):
            continue
        target = pathlib.PurePosixPath(pattern.strip('/'))  # repo-relative; ignores leading slash
        entries[target] = Entry(pattern=pattern, owners=tuple(owners))
    return entries


def tracked_files(root: pathlib.Path) -> list[str]:
    """Return the repo-relative POSIX paths of all files tracked by git in `root`.

    Only tracked files are returned, so untracked and ignored paths (e.g. `.venv/`, caches)
    don't need a CODEOWNERS entry.
    """
    output = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root, text=True)
    return [file for file in output.split('\0') if file]


def find_unowned_dirs(
    entries: dict[pathlib.PurePosixPath, Entry], files: list[pathlib.PurePosixPath]
) -> list[pathlib.PurePosixPath]:
    """Return the paths to check that have no CODEOWNERS entry, directly or via all their children.

    The paths to check are every top-level path and every immediate child of `interfaces/`. A
    path passes if it has its own entry, or (for a directory) every one of its immediate children
    has its own entry. An entry without an owner still counts: such a path is explicitly disowned
    (like `interfaces/index.json`), which is a deliberate decision. This check is not recursive,
    so a grandchild entry never satisfies a child, and the catch-all `*` entry was dropped by the
    parser, so it never stands in for an explicit one.
    """
    targets = [*children_of(ROOT, files), *children_of(pathlib.PurePosixPath('interfaces'), files)]
    unowned: list[pathlib.PurePosixPath] = []
    for path in targets:
        children = children_of(path, files)
        if path not in entries and not (children and entries.keys() >= set(children)):
            unowned.append(path)
    return sorted(unowned)


def children_of(
    directory: pathlib.PurePosixPath, files: list[pathlib.PurePosixPath]
) -> list[pathlib.PurePosixPath]:
    """Return the immediate children (files and subdirectories) of `directory` tracked in `files`.

    `directory` may be `ROOT` (the repository root). A child is the path one level below
    `directory` on the way to a tracked file.
    """
    children = {
        directory / file.relative_to(directory).parts[0]
        for file in files
        if directory == ROOT or directory in file.parents
    }
    return sorted(children)


def render(path: pathlib.PurePosixPath, files: list[pathlib.PurePosixPath]) -> str:
    """Render `path` in CODEOWNERS form: a leading `/`, plus a trailing `/` if it's a directory."""
    return f'/{path}/' if children_of(path, files) else f'/{path}'


def find_bad_entries(
    entries: dict[pathlib.PurePosixPath, Entry], root: pathlib.Path
) -> list[Entry]:
    """Return the entries that don't point at an existing path of the right kind.

    An entry is bad if its target doesn't exist, or if its trailing slash disagrees with
    reality: directory entries must end with `/` and file entries must not. This enforces the
    convention that every directory entry carries a trailing slash.
    """
    bad: list[Entry] = []
    for target, entry in entries.items():
        path = root / target
        if not path.exists() or path.is_dir() != entry.pattern.endswith('/'):
            bad.append(entry)
    return bad


if __name__ == '__main__':
    sys.exit(main())
