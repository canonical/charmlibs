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

Exits non-zero if the version is not found, so the caller notices the
missing changelog entry rather than publishing an empty release body.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

_HEADING = re.compile(r'^(?P<hashes>#{1,6})[ \t]+(?P<title>\S.*)$')
_FENCE = re.compile(r'^(?P<fence>`{3,}|~{3,})')


def _headings(text: str) -> list[tuple[int, int, int]]:
    """Return (level, start, end) for each heading outside a fenced code block.

    A changelog entry for a breaking change tends to carry a before/after
    example, and a Python comment inside that example starts with a '#'. Scanned
    line by line rather than with one MULTILINE regex, a '# Before' inside a
    fence would end the section there: the release notes would lose the example
    and everything after it, and end on an unterminated fence.
    """
    headings: list[tuple[int, int, int]] = []
    fence = ''
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        match = _FENCE.match(stripped)
        if match:
            candidate = match.group('fence')
            if not fence:
                fence = candidate
            elif candidate[0] == fence[0] and len(candidate) >= len(fence):
                # A closing fence is the same character and at least as long.
                fence = ''
        elif not fence:
            heading = _HEADING.match(line)
            if heading:
                headings.append((
                    len(heading.group('hashes')),
                    offset + indent,
                    offset + len(line.rstrip('\n')),
                ))
        offset += len(line)
    return headings


def _version_of(title: str) -> str:
    """Return the version a heading names, or '' if it doesn't name one.

    Keep a Changelog brackets the version, so strip those.
    """
    return title.split()[0].strip('[]')


def extract(text: str, version: str) -> str | None:
    """Return the CHANGELOG section for ``version``, or ``None`` if absent."""
    headings = _headings(text)
    for i, (level, start, end) in enumerate(headings):
        title = _HEADING.match(text[start:end])
        assert title is not None  # `_headings` only returns what `_HEADING` matched.
        if _version_of(title.group('title')) != version:
            continue
        section_end = len(text)
        for later_level, later_start, _ in headings[i + 1 :]:
            if later_level <= level:
                section_end = later_start
                break
        return text[end:section_end].strip()
    return None


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and print the requested changelog section."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('changelog', type=pathlib.Path, help='Path to CHANGELOG.md.')
    parser.add_argument('version', help='Version to extract (e.g. 1.3.0.post0).')
    args = parser.parse_args(argv)

    section = extract(args.changelog.read_text(), args.version)
    if section is None:
        print(
            f'Version {args.version!r} not found in {args.changelog}',
            file=sys.stderr,
        )
        return 1

    print(section)
    return 0


if __name__ == '__main__':
    sys.exit(main())
