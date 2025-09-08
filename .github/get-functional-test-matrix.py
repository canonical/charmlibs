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
# requires-python = '>=3.10'
# dependencies = [
#     'tomli',
# ]
# ///

"""Generate functional test matrix from package's pyproject.toml.

Assumes that the current working directory is the project root.
The package name must be provided as a positional commandline argument.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib

import tomli


def _parse_args() -> pathlib.Path:
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=pathlib.Path)
    args = parser.parse_args()
    return args.package


def _main(package: pathlib.Path) -> None:
    matrix = _get_matrix(package)
    line = f'matrix={json.dumps(matrix)}'
    print(line)
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(line, file=f)


def _get_matrix(package: pathlib.Path) -> dict[str, list[str]]:
    pyproject_toml = tomli.loads((package / 'pyproject.toml').read_text())
    table = pyproject_toml.get('tool', {}).get('charmlibs', {}).get('functional', {})
    return {
        'ubuntu': [f'ubuntu-{v}' for v in table.get('ubuntu') or ['latest']],
        'sudo': ['sudo'] if table.get('sudo') else ['no-sudo'],
        'pebble': [f'pebble@{v}' for v in table.get('pebble', [])] or ['no-pebble'],
    }


if __name__ == '__main__':
    _main(package=_parse_args())
