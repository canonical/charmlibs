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

"""Exit with success if every testing package agrees with its library about the version.

A library and its testing package are released in lockstep, so the version appears in four
places that must all agree::

    <library>/src/.../_version.py                 the library's own version
    <library>/testing/src/.../_version.py         the testing package's own version
    <library>/pyproject.toml                      testing extra, pinning the testing package
    <library>/testing/pyproject.toml              dependency, pinning the library

Checking only the first two would let a release ship with a pin pointing at a version that
doesn't exist yet, so all four are checked here.

Otherwise exit with failure and output every disagreement to stdout.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import typing

import tomllib

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_TESTING_SUFFIX = '-testing'


def _normalize(name: str) -> str:
    """Normalize a distribution name according to PyPI rules.

    https://packaging.python.org/en/latest/specifications/name-normalization/
    """
    return re.sub(r'[-_.]+', '-', name).lower().strip()


def _pinned_version(requirement: str) -> str | None:
    """Return the version an ``==`` requirement pins, or ``None`` if it isn't one."""
    _, separator, version = requirement.partition('==')
    return version.strip() or None if separator else None


def _find_pin(requirements: list[str], dist: str) -> tuple[str, str | None] | None:
    """Return the requirement on ``dist`` and the version it pins, or ``None`` if absent.

    ``None`` for the version means the requirement is there but doesn't pin exactly.
    """
    for requirement in requirements:
        # Strip any extras and environment markers before comparing the name.
        name = re.split(r'[\[;=<>!~ ]', requirement, maxsplit=1)[0]
        if _normalize(name) == dist:
            return requirement, _pinned_version(requirement)
    return None


def _strings(value: object) -> list[str]:
    """Return the strings in ``value``, ignoring anything else.

    A hand-written pyproject.toml can hold anything at all, so the shape is checked rather
    than asserted -- a malformed dependency list should surface as a missing pin below,
    named and explained, rather than as a traceback here.
    """
    if not isinstance(value, list):
        return []
    return [item for item in typing.cast('list[object]', value) if isinstance(item, str)]


def _requirements(pyproject: dict[str, typing.Any], extra: str | None = None) -> list[str]:
    """Return ``project.dependencies``, or the named ``optional-dependencies`` extra."""
    project: dict[str, typing.Any] = pyproject.get('project', {})
    if extra is None:
        return _strings(project.get('dependencies', []))
    optional: dict[str, typing.Any] = project.get('optional-dependencies', {})
    return _strings(optional.get(extra, []))


def _check_pin(
    *, pyproject_path: pathlib.Path, requirements: list[str], dist: str, version: str, what: str
) -> list[str]:
    """Return a list of problems with how ``pyproject_path`` pins ``dist`` at ``version``."""
    relative = pyproject_path.relative_to(_REPO_ROOT)
    found = _find_pin(requirements, dist)
    if found is None:
        return [f'{relative}: no {what} on {dist}']
    requirement, pinned = found
    if pinned is None:
        return [f'{relative}: {what} {requirement!r} should pin {dist}=={version}']
    if pinned != version:
        return [f'{relative}: {what} pins {dist}=={pinned}, but {dist} is {version}']
    return []


def _main() -> None:
    ls = pathlib.Path(__file__).parent / 'ls.py'
    cmd = [ls, 'packages', '--output=path', '--output=name', '--output=version']
    infos = json.loads(subprocess.check_output(cmd))
    versions = {_normalize(i['name']): i['version'] for i in infos}
    paths = {_normalize(i['name']): pathlib.Path(i['path']) for i in infos}
    problems: list[str] = []
    for testing_dist in sorted(d for d in versions if d.endswith(_TESTING_SUFFIX)):
        library_dist = testing_dist.removesuffix(_TESTING_SUFFIX)
        if library_dist not in versions:
            problems.append(f'{testing_dist}: no library package named {library_dist}')
            continue
        testing_version = versions[testing_dist]
        library_version = versions[library_dist]
        if library_version != testing_version:
            problems.append(
                f'{library_dist} ({library_version}) != {testing_dist} ({testing_version})'
            )
            # The pins below can only be right for one of the two, so don't pile on.
            continue
        library_pyproject = _REPO_ROOT / paths[library_dist] / 'pyproject.toml'
        testing_pyproject = _REPO_ROOT / paths[testing_dist] / 'pyproject.toml'
        with library_pyproject.open('rb') as f:
            library = tomllib.load(f)
        with testing_pyproject.open('rb') as f:
            testing = tomllib.load(f)
        problems.extend(
            _check_pin(
                pyproject_path=library_pyproject,
                requirements=_requirements(library, extra='testing'),
                dist=testing_dist,
                version=testing_version,
                what='testing extra',
            )
        )
        problems.extend(
            _check_pin(
                pyproject_path=testing_pyproject,
                requirements=_requirements(testing),
                dist=library_dist,
                version=library_version,
                what='dependency',
            )
        )
    for problem in problems:
        print(problem)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    _main()
