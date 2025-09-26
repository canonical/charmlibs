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

"""Output the packages to publish, the PyPI repository-url and whether to skip Juju tests."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys


def _main() -> None:
    event_name = os.environ['GITHUB_EVENT_NAME']
    event = json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if event_name == 'push':
        cmd = [
            '.scripts/ls.py',
            'packages',
            event['before'],
            os.environ['GITHUB_SHA'],
            '--exclude-examples',
            '--only-if-version-changed',
        ]
        _output({
            'packages': subprocess.check_output(cmd, text=True).strip(),
            'skip-juju': 'false',
            'repository-url': 'https://upload.pypi.org/legacy/',
        })
    elif event_name == 'workflow_dispatch':
        _output({
            'packages': json.dumps([event['inputs']['package']]),
            'skip-juju': event['inputs']['skip-juju'],
            'repository-url': 'https://test.pypi.org/legacy/',
        })
    else:
        print(f'Unexpected event name: {event_name}')
        sys.exit(1)


def _output(di: dict[str, str]) -> None:
    for v in di.values():
        if not isinstance(v, str):  # type: ignore
            print(f'Unexpected type {type(v)} for value: v')
            sys.exit(1)
    output = '\n'.join(f'{k}={v}' for k, v in di.items())
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(output)
        print(output, file=f)


if __name__ == '__main__':
    _main()
