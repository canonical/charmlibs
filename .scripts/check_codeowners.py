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

# `.scripts/check_codeowners.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TrackedFiles:
    def __init__(self):
        self._files = self._get_tracked_files()
        self._lookup: set[pathlib.Path] = set()
        self._highest_lookup_depth = 0

    def _get_tracked_files(self) -> list[pathlib.Path]:
        output = subprocess.check_output(['git', 'ls-files', '-z'], cwd=REPO_ROOT, text=True)
        return [pathlib.Path(file) for file in output.split('\0') if file]

    def children(self, path: pathlib.Path) -> list[pathlib.Path]:
        """Return the immediate children of `path` that are tracked files or directories."""
        for i in range(self._highest_lookup_depth + 1, len(path.parts) + 2):
            self._lookup.update(pathlib.Path(*p.parts[:i]) for p in self._files)
            self._highest_lookup_depth = i
        return sorted(
            rel_path
            for p in path.iterdir()
            if (rel_path := p.relative_to(REPO_ROOT)) in self._lookup
        )


def main() -> int:
    """Run both CODEOWNERS checks, printing any problems and returning the problem count."""
    entries = parse_codeowners((REPO_ROOT / 'CODEOWNERS').read_text())
    tracked = TrackedFiles()
    owner_required = [*tracked.children(REPO_ROOT), *tracked.children(REPO_ROOT / 'interfaces')]
    problems = 0
    # Check tracked files against CODEOWNERS entries.
    for path in owner_required:
        if path not in entries:
            if not path.is_dir():
                print(f'No explicit CODEOWNERS for: /{path}')
                problems += 1
            elif not all(p in entries for p in tracked.children(REPO_ROOT / path)):
                print(f"No explicit CODEOWNERS for: /{path}/ (and its children aren't all owned)")
                problems += 1
    # Check CODEOWNERS entries.
    for target, pattern in entries.items():
        path = REPO_ROOT / target
        if not path.exists():
            print(f'CODEOWNERS entry points at a missing path: {pattern}')
            problems += 1
        if path.is_dir() != pattern.endswith('/'):
            print(f'CODEOWNERS entry must have a trailing slash iff it is a dir: {pattern}')
            problems += 1
        if not pattern.startswith('/'):
            print(f'CODEOWNERS entry must be anchored with a leading /: {pattern}')
            problems += 1
    if not problems:
        print('No problems found in CODEOWNERS :)')
    return problems


def parse_codeowners(text: str) -> dict[pathlib.Path, str]:
    """Parse CODEOWNERS into a `{target: pattern}` dict, keyed by the repo-relative path it covers.

    Comments, blanks, and wildcard patterns (containing any of `*?[]`, such as the catch-all `*`)
    are ignored: wildcards aren't anchored paths, so this check neither validates nor counts them.
    Keys are `pathlib.Path`s, so a trailing slash on a directory entry doesn't affect lookups.
    """
    entries: dict[pathlib.Path, str] = {}
    for line in text.splitlines():
        entry, _, *_ = line.partition('#')  # drop trailing comment
        entry = entry.strip()
        if not entry:
            continue
        pattern, *_owners = entry.split()
        if any(char in pattern for char in '*?[]'):
            continue
        target = pathlib.Path(pattern.strip('/'))  # to be interpreted relative to REPO_ROOT
        entries[target] = pattern
    return entries


if __name__ == '__main__':
    sys.exit(main())
