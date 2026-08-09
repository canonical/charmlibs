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

Package CHANGELOGs in this repo use one ``# <version> - <date>`` heading per
release. Given a CHANGELOG path and a version string, print the block from
that heading up to the next ``# `` heading (exclusive), so that a release
workflow can pass it to ``gh release create --notes-file`` and give
dependabot something useful to render for a single-package version bump.

Exits non-zero if the version is not found, so the caller notices the
missing changelog entry rather than publishing an empty release body.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


def extract(text: str, version: str) -> str | None:
    """Return the CHANGELOG section for ``version``, or ``None`` if absent."""
    heading = re.compile(r'^# (?P<version>\S+)\b.*$', re.MULTILINE)
    matches = list(heading.finditer(text))
    for i, match in enumerate(matches):
        if match.group('version') == version:
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return None


def main() -> int:
    """Parse CLI arguments and print the requested changelog section."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('changelog', type=pathlib.Path, help='Path to CHANGELOG.md.')
    parser.add_argument('version', help='Version to extract (e.g. 1.3.0.post0).')
    args = parser.parse_args()

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
