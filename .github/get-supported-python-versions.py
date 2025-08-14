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

# /// script
# requires-python = '>=3.8'
# dependencies = [
#     'packaging',
#     'tomli',
# ]
# ///

"""Output the subset of Python versions used in testing that the provided package supports.

Assumes that the current working directory is the project root.
The package name must be provided as a positional commandline argument.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib

import packaging.specifiers
import tomli

VERSIONS = [
    '3.8',  # Ubuntu 20.04  (ops 2)
    '3.10',  # Ubuntu 22.04  (ops 3)
    '3.12',  # Ubuntu 24.04
    '3.13',  # latest Python release
]


def _parse_args() -> pathlib.Path:
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=pathlib.Path)
    args = parser.parse_args()
    return args.package


def _main(package: str) -> None:
    versions = _get_supported_python_versions(package=package)
    line = f'versions={json.dumps(versions)}'
    print(line)
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(line, file=f)


def _get_supported_python_versions(package: pathlib.Path) -> dict[str, list[str]]:
    pyproject_toml = tomli.loads((package / 'pyproject.toml').read_text())
    requires_python = pyproject_toml['project']['requires-python']
    version_set = packaging.specifiers.SpecifierSet(requires_python)
    supported_versions = [v for v in VERSIONS if v in version_set]
    assert supported_versions, f'No version from {VERSIONS} matches {requires_python}!'
    return {
        'lint': supported_versions,
        'unit': supported_versions,
        'pebble': (
            [supported_versions[0], supported_versions[-1]]
            if len(supported_versions) > 1
            else supported_versions
        ),
    }


if __name__ == '__main__':
    _main(package=_parse_args())
