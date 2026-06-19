#!/usr/bin/env -S uv run --script --no-project

# Copyright 2024 Canonical Ltd.
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

"""Check that a PR title follows the Conventional Commits specification.

Reads the PR title from the PR_TITLE environment variable.
Exits with a non-zero status and prints an error message if the title is invalid.

Reference: https://www.conventionalcommits.org/en/v1.0.0/
"""

from __future__ import annotations

import os
import re
import sys

_TYPES = frozenset({
    'build',
    'chore',
    'ci',
    'docs',
    'feat',
    'fix',
    'perf',
    'refactor',
    'revert',
    'style',
    'test',
})

# <type>[optional scope][optional !]: <description>
_PATTERN = re.compile(
    r'^(?P<type>[A-Za-z]+)'  # lower-case only, but let this be validated by _TYPES
    r'(?:\((?P<scope>[^()]+)\))?'
    r'(?P<breaking>!)?'
    r': '
    r'(?P<description>.+)$'
)


def _main() -> None:
    title = os.environ.get('PR_TITLE', '').strip()
    if not title:
        print('PR_TITLE environment variable is not set or empty.', file=sys.stderr)
        sys.exit(1)

    match = _PATTERN.match(title)
    if not match:
        print(
            f'PR title does not follow Conventional Commits format.\n'
            f'Expected: <type>[(<scope>)][!]: <description>\n'
            f'Got: {title!r}\n'
            'Read more: https://github.com/canonical/charmlibs/blob/main/CONTRIBUTING.md#pull-requests',
            file=sys.stderr,
        )
        sys.exit(1)

    commit_type = match.group('type')
    if commit_type not in _TYPES:
        print(
            f'Invalid type {commit_type!r} in PR title.\n'
            f'Valid types: {", ".join(sorted(_TYPES))}\n'
            f'Got: {title!r}'
            'Read more: https://github.com/canonical/charmlibs/blob/main/CONTRIBUTING.md#pull-requests',
            file=sys.stderr,
        )
        sys.exit(1)

    print(f'OK: {title!r}')


if __name__ == '__main__':
    _main()
