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
   or removing a directory can't leave behind an orphan entry.

Exit with success (0) if both checks pass, otherwise print the problems to stdout
and exit with failure (the number of problems found).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

# `.scripts/check_codeowners.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CODEOWNERS = REPO_ROOT / 'CODEOWNERS'


def main() -> int:
    """Run both CODEOWNERS checks, printing any problems and returning the problem count."""
    entries = parse_codeowners(CODEOWNERS.read_text())
    paths = build_paths(tracked_files(REPO_ROOT))
    problems = 0
    for path in find_unowned_dirs(entries, paths):
        print(f'No explicit CODEOWNERS entry for: /{path}')
        problems += 1
    for pattern in find_orphan_entries(entries, REPO_ROOT):
        print(f'CODEOWNERS entry points at a missing path: {pattern}')
        problems += 1
    if problems == 0:
        print('Every path has a CODEOWNERS owner, and no entries are orphaned.')
    return problems


class Entry(typing.NamedTuple):
    """A single CODEOWNERS entry: a path pattern and its owners."""

    pattern: str
    owners: tuple[str, ...]


class Path(typing.NamedTuple):
    """A repo path to check, with its immediate children.

    `path` is relative to the repo root; directory paths end with `/`. `child_paths` are the
    immediate children (also repo-relative, directories ending with `/`), and is empty for
    files and for directories with no tracked children.
    """

    path: str
    child_paths: tuple[str, ...]


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


def tracked_files(root: pathlib.Path) -> list[str]:
    """Return the repo-relative POSIX paths of all files tracked by git in `root`.

    Only tracked files are returned, so untracked and ignored paths (e.g. `.venv/`, caches)
    don't need a CODEOWNERS entry.
    """
    output = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root, text=True)
    return [file for file in output.split('\0') if file]


def build_paths(files: Iterable[str]) -> list[Path]:
    """Build the `Path`s to check from a list of repo-relative tracked file paths.

    Returns an item for every top-level entry and every immediate child of `interfaces/`. A
    directory's `path` ends with `/` and its `child_paths` list its immediate children (also
    with a trailing `/` for directories); files have an empty `child_paths`.
    """
    children: dict[str, set[str]] = {}  # parent prefix -> immediate child names
    is_dir: dict[str, bool] = {}  # path component prefix -> whether it has children
    for file in files:
        parts = file.split('/')
        for depth in range(len(parts)):
            parent = '/'.join(parts[:depth])
            name = parts[depth]
            children.setdefault(parent, set()).add(name)
            is_dir[f'{parent}/{name}' if parent else name] = depth < len(parts) - 1

    def render(prefix: str, name: str) -> str:
        path = f'{prefix}/{name}' if prefix else name
        return f'{path}/' if is_dir[path] else path

    def child_paths(prefix: str, name: str) -> tuple[str, ...]:
        path = f'{prefix}/{name}' if prefix else name
        return tuple(sorted(render(path, child) for child in children.get(path, ())))

    paths = [Path(render('', name), child_paths('', name)) for name in children.get('', ())]
    paths += [
        Path(render('interfaces', name), child_paths('interfaces', name))
        for name in children.get('interfaces', ())
    ]
    return sorted(paths)


def find_unowned_dirs(entries: Iterable[Entry], paths: Iterable[Path]) -> list[str]:
    """Return the paths without a CODEOWNERS entry, directly or via all their children.

    A path passes if it has its own entry, or (for a directory) every one of its immediate
    children has its own entry. An entry without an owner counts: such a path is explicitly
    disowned (like `interfaces/index.json`), which is a deliberate decision. This check is not
    recursive, so a grandchild entry never satisfies a child, and the catch-all `*` entry isn't a
    path entry, so it never stands in for an explicit one.
    """
    entry_targets = {target for entry in entries if (target := entry_target(entry.pattern))}

    def has_entry(path: str) -> bool:
        return pathlib.PurePosixPath(path) in entry_targets

    unowned: list[str] = []
    for item in paths:
        if has_entry(item.path):
            continue
        if item.child_paths and all(has_entry(child) for child in item.child_paths):
            continue
        unowned.append(item.path)
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
