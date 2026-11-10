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


def _version_of(title: str) -> str:
    """Return the version a heading names, or '' if it doesn't name one.

    Keep a Changelog brackets the version, so strip those.
    """
    return title.split()[0].strip('[]')


def _sections(text: str) -> dict[str, list[str]]:
    """Map each heading's version to the lines of its section.

    A section runs to the next heading at the same level or shallower, so a
    version's ``### Fixed``-style subheadings stay in its body. If a version
    appears more than once, the first section wins.

    Headings inside fenced code blocks are ignored. A changelog entry for a
    breaking change tends to carry a before/after example, and a Python comment
    inside that example starts with a '#': taken as a heading, a '# Before'
    would end the section there, and the release notes would lose the example
    and everything after it, and end on an unterminated fence.
    """
    sections: dict[str, list[str]] = {}
    open_sections: list[tuple[int, list[str]]] = []  # (level, lines) still collecting
    fence = ''
    for line in text.splitlines():
        match = _FENCE.match(line.lstrip())
        if match:
            candidate = match.group('fence')
            if not fence:
                fence = candidate
            elif candidate[0] == fence[0] and len(candidate) >= len(fence):
                # A closing fence is the same character and at least as long.
                fence = ''
        elif not fence and (heading := _HEADING.match(line)):
            level = len(heading.group('hashes'))
            # A heading closes any open section at the same level or deeper.
            open_sections = [(lvl, lines) for lvl, lines in open_sections if lvl < level]
            for _, lines in open_sections:
                lines.append(line)
            version = _version_of(heading.group('title'))
            if version not in sections:
                sections[version] = []
                open_sections.append((level, sections[version]))
            continue
        for _, lines in open_sections:
            lines.append(line)
    return sections


def extract(text: str, version: str) -> str | None:
    """Return the CHANGELOG section for ``version``, or ``None`` if absent."""
    lines = _sections(text).get(version)
    return None if lines is None else '\n'.join(lines).strip()


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
