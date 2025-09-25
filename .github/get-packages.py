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

"""Output changed packages, or all packages if global config files have changed."""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess

_GLOBAL_FILES = {'.github', 'justfile', 'pyproject.toml'}


def _parse_args() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument('git_base_ref', nargs='?', default='')
    args = parser.parse_args()
    return args.git_base_ref


def _main(git_base_ref: str) -> None:
    cmd = ['.scripts/ls.py', 'packages']
    if not git_base_ref:
        print('Using all packages because no git base ref was provided:')
    elif global_changes := _get_global_changes(git_base_ref):
        print(f'Using all packages because global files were changed: {global_changes}')
    else:
        cmd.append(git_base_ref)
    packages = subprocess.check_output(cmd, text=True).strip()
    line = f'packages={packages}'
    print(line)
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(line, file=f)


def _get_global_changes(git_base_ref: str) -> list[str]:
    cmd = ['git', 'diff', '--name-only', git_base_ref]
    changes = subprocess.check_output(cmd, text=True).strip().splitlines()
    return sorted(_GLOBAL_FILES.intersection(c.split('/')[0] for c in changes))


if __name__ == '__main__':
    _main(git_base_ref=_parse_args())
