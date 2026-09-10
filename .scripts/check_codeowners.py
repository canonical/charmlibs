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
   (for a directory) every one of its immediate children has a direct entry.
2. Every concrete CODEOWNERS entry corresponds to a real path in the repository, so renaming
   or removing a directory can't leave behind a bad entry.

Exit with success (0) if both checks pass, otherwise print the problems to stdout
and exit with failure (the number of problems found).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

# `.scripts/check_codeowners.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    """Run both CODEOWNERS checks, printing any problems and returning the problem count."""
    entries = parse_codeowners((REPO_ROOT / 'CODEOWNERS').read_text())
    children = map_children(get_tracked_files(REPO_ROOT))
    problems = check(entries, children)
    if problems:
        print('\n'.join(problems))
    else:
        print('No problems found with CODEOWNERS :)')
    return len(problems)


def parse_codeowners(text: str) -> dict[pathlib.Path, str]:
    """Parse CODEOWNERS into a `{target: pattern}` dict, keyed by the repo-relative path it covers.

    Comments, blanks, and wildcard patterns (containing any of `*?[]`) are ignored.
    """
    entries: dict[pathlib.Path, str] = {}
    for line in text.splitlines():
        entry, _, _ = line.partition('#')  # drop trailing comments
        entry = entry.strip()
        if not entry:
            continue
        pattern, *_owners = entry.split()
        if any(char in pattern for char in '*?[]'):
            continue
        target = pathlib.Path(pattern.strip('/'))  # to be interpreted relative to REPO_ROOT
        entries[target] = pattern
    return entries


def get_tracked_files(root: pathlib.Path | str) -> list[pathlib.Path]:
    """Return the repo-relative paths of all files tracked by git in `root`."""
    output = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root, text=True)
    return [pathlib.Path(file) for file in output.split('\0') if file]


def map_children(files: list[pathlib.Path]) -> dict[pathlib.Path, list[pathlib.Path]]:
    """Map each tracked directory to its sorted immediate children (files and subdirectories).

    The repository root is keyed as `pathlib.Path()` (i.e. `.`). A path is a directory iff it
    appears as a key; the tracked files are the paths that never appear as keys.
    """
    children: dict[pathlib.Path, set[pathlib.Path]] = {}
    for path in files:
        for p in (path, *path.parents[:-1]):  # Don't include the root as a child ('.').
            children.setdefault(p.parent, set()).add(p)
    return {k: sorted(v) for k, v in children.items()}


def check(
    entries: dict[pathlib.Path, str], children: dict[pathlib.Path, list[pathlib.Path]]
) -> list[str]:
    """Return a list of problems found between the CODEOWNERS `entries` and the tracked tree.

    Everything is checked against the tracked tree (`children`) rather than the filesystem, so
    untracked and ignored paths are irrelevant. A path is a tracked directory iff it's a key in
    `children`; `all_paths` is every tracked file and directory.
    """
    problems: list[str] = []
    # Check that each top-level path and immediate child of interfaces/ is owned.
    for path in *children[pathlib.Path()], *children[pathlib.Path('interfaces')]:
        if path in entries:
            continue
        if path not in children:  # a file: it needs its own entry
            problems.append(f'No explicit CODEOWNERS for: /{path}')
        elif not all(child in entries for child in children[path]):
            problems.append(
                f"No explicit CODEOWNERS for: /{path}/ (and its children aren't all owned)"
            )
    # Check that each entry points at a tracked path of the matching kind.
    all_paths = {child for siblings in children.values() for child in siblings}
    for target, pattern in entries.items():
        if target not in all_paths:
            problems.append(f'CODEOWNERS entry points at a missing path: {pattern}')
        elif (target in children) != pattern.endswith('/'):
            problems.append(
                f'CODEOWNERS entry must have a trailing slash iff it is a dir: {pattern}'
            )
        if not pattern.startswith('/'):
            problems.append(f'CODEOWNERS entry must be anchored with a leading /: {pattern}')
    return problems


if __name__ == '__main__':
    sys.exit(main())
