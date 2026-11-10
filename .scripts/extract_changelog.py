#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = [
# ]
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

"""Print a single version's section from a package CHANGELOG.md.

Given a CHANGELOG path and a version string, print the block for that
version, so that a release workflow can pass it to ``gh release create
--notes-file`` and give dependabot something useful to render for a
single-package version bump.

CHANGELOGs in this repo do not all look the same. Most packages use one
``# <version> - <date>`` heading per release, but the interfaces packages
open with a prose ``# Changelog`` and put versions at H2, and a couple of
them follow Keep a Changelog and bracket the version: ``## [0.5.0] - ...``.
So a heading at any level counts if its first word, with any surrounding
brackets removed, is the version we want, and its section runs to the next
heading at the same level or shallower.

Exits non-zero if the version is not found or its section is empty, so the
caller notices the missing changelog entry rather than publishing an empty
release body.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterator


class _Heading(NamedTuple):
    level: int
    version: str


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and print the requested changelog section."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('changelog', type=pathlib.Path, help='Path to CHANGELOG.md.')
    parser.add_argument('version', help='Version to extract (e.g. 1.3.0.post0).')
    args = parser.parse_args(argv)
    section = extract(args.changelog.read_text(), args.version)
    if section is None:
        msg = f'Version {args.version!r} not found in {args.changelog}'
        print(msg, file=sys.stderr)
        return 1
    if not section:
        msg = f'Version {args.version!r} has an empty section in {args.changelog}'
        print(msg, file=sys.stderr)
        return 1
    print(section)
    return 0


def extract(text: str, version: str) -> str | None:
    """Return the CHANGELOG section for ``version``, or ``None`` if absent.

    A heading with nothing under it gives an empty string.
    If the version has more than one heading, the first one wins.
    """
    lines = _iter(text)
    # Find the heading for this version.
    for _, heading in lines:
        if heading and heading.version == version:
            break
    else:  # No break, so no heading matched this version.
        return None
    # Collect and return the lines for this version.
    body: list[str] = []
    for line, other in lines:
        if other and other.level <= heading.level:
            break
        body.append(line)
    return '\n'.join(body).strip()


def _iter(text: str) -> Iterator[tuple[str, _Heading | None]]:
    """Yield each line of a changelog and heading data if it is a heading.

    Lines inside fenced code blocks are never headings. A changelog entry for a
    breaking change tends to carry a before/after example, and a Python comment
    in it starts with a '#': taken as a heading, a '# Before' would end the
    section there, and the release notes would lose the example and everything
    after it.

    A fence opens on three or more backticks or tildes, optionally followed by
    an info string ('```python'). It closes on a line of only the same
    character, at least as long, so a '```python' inside a '```' block is
    content, not a close.
    """
    fence_re = re.compile(r'^(?P<fence>`{3,}|~{3,})')
    heading_re = re.compile(r'^(?P<hashes>#{1,6})[ \t]+(?P<title>\S.*)$')
    fence = ''  # The current code-fenced section's delimiter.
    for line in text.splitlines():
        heading = None
        stripped = line.strip()
        if fence:  # We're currently in a code-fenced section.
            # If a line is a fence of equal or greater depth, the section ends.
            if stripped.startswith(fence) and not stripped.strip(fence[0]):
                fence = ''
        # We're not in a code-fenced section, so check if one is starting.
        elif match := fence_re.match(stripped):
            fence = match['fence']
        # We're not in or starting a code-fenced section, check if we're on a heading line.
        elif match := heading_re.match(line):
            # Keep a Changelog brackets the version: '## [0.5.0] - 2026-01-01'.
            version = match['title'].split()[0].strip('[]')
            heading = _Heading(level=len(match['hashes']), version=version)
        yield line, heading


if __name__ == '__main__':
    sys.exit(main())
