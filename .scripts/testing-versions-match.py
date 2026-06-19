#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = [
# ]
# ///

# Copyright 2025 Canonical Ltd.
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

"""Exit with success if all testing packages match their main package's version.

Otherwise exit with failure and output all non-matching packages to stdout.
"""

import json
import pathlib
import subprocess
import sys


def _main() -> None:
    # Get package names and versions.
    ls = pathlib.Path(__file__).parent / 'ls.py'
    cmd = [ls, 'packages', '--output=name', '--output=version']
    infos = json.loads(subprocess.check_output(cmd))
    # Split into main packages and testing packages.
    main_packages: dict[str, str] = {}
    testing_packages: dict[str, str] = {}
    for i in infos:
        name = i['name']
        version = i['version']
        if name.endswith('-testing'):
            testing_packages[name] = version
        else:
            main_packages[name] = version
    # Output any mismatches and exit accordingly.
    errors = 0
    for name, version in sorted(testing_packages.items()):
        main_package_name = name.removesuffix('-testing')
        main_package_version = main_packages[main_package_name]
        if main_package_version != version:
            print(f'{main_package_name} ({main_package_version}) != {name} ({version})')
            errors += 1
    sys.exit(errors)


if __name__ == '__main__':
    _main()
