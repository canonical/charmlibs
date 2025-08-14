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

"""Output the package, PyPI repository-url and whether to skip Juju tests when publishing."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys


def _main() -> None:
    event_name = os.environ['GITHUB_EVENT_NAME']
    if event_name == 'push':
        _output({
            'package': _parse_tag(os.environ['GITHUB_REF']),
            'skip-juju': 'false',
            'repository-url': 'https://upload.pypi.org/legacy/',
        })
    elif event_name == 'workflow_dispatch':
        event = json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        _output({
            'package': event['inputs']['package'],
            'skip-juju': event['inputs']['skip-juju'],
            'repository-url': 'https://test.pypi.org/legacy/',
        })
    else:
        print(f'Unexpected event name: {event_name}')
        sys.exit(1)


def _parse_tag(ref: str) -> str:
    tag_prefix = 'refs/tags/'
    if not ref.startswith(tag_prefix):
        print(f'Unexpected ref: {ref}')
        sys.exit(1)
    tag = ref[len(tag_prefix) :]
    match = re.match(r'^(.*)-v[0-9]+.*$', tag)
    if match is None:
        print(f'Malformed tag: {tag}')
        sys.exit(1)
    package = match.group(1)
    if package == 'charmlibs':
        return '.package'
    if package == 'interfaces':
        return 'interfaces/.package'
    if package.startswith('interfaces-'):
        return package.replace('-', '/', 1)  # interfaces-foo-bar -> interfaces/foo-bar
    return package


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
