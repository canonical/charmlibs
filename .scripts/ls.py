#!/usr/bin/env -S uv run --script --no-project

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

"""Output the packages in the repository as a json list.

See the the commandline help for more options.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import json
import logging
import pathlib
import subprocess
import tarfile
import tempfile

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_INTERFACES = _REPO_ROOT / 'interfaces'

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


@dataclasses.dataclass
class _Args:
    kind: str
    refs: tuple[str, str | None] | None
    include_examples: bool
    include_placeholders: bool
    only_if_version_changed: bool

    @classmethod
    def from_cli(cls) -> _Args:
        parser = argparse.ArgumentParser()
        parser.add_argument('kind', choices=('packages', 'interfaces'))
        parser.add_argument('old_ref', nargs='?')
        parser.add_argument('new_ref', nargs='?')
        parser.add_argument('--exclude-examples', action='store_true')
        parser.add_argument('--exclude-placeholders', action='store_true')
        parser.add_argument('--only-if-version-changed', action='store_true')
        args = parser.parse_args()
        return cls(
            kind=args.kind,
            refs=(args.old_ref, args.new_ref) if args.old_ref is not None else None,
            include_examples=not args.exclude_examples,
            include_placeholders=not args.exclude_placeholders,
            only_if_version_changed=args.only_if_version_changed,
        )


def _ls(args: _Args) -> list[str]:
    include: list[str] = []
    if args.include_examples:
        include.extend(('.example', '.tutorial'))
    if args.include_placeholders:
        include.append('.package')
    # collect packages or interfaces
    if args.kind == 'packages':
        dirs = _packages(include=include)
    elif args.kind == 'interfaces':
        dirs = _interfaces(include=include)
    else:
        raise ValueError(f'Unknown value for `kind` {args}')
    # filter based on changes
    if args.refs:
        old_ref, new_ref = args.refs
        dirs = _changed_only(dirs, old_ref=old_ref, new_ref=new_ref)
        if args.only_if_version_changed and args.kind == 'packages':
            dirs = _changed_version_only(dirs, old_ref=old_ref, new_ref=new_ref)
    return [str(p) for p in dirs]


def _packages(include: list[str]) -> list[pathlib.Path]:
    paths: set[pathlib.Path] = set()
    for root in _REPO_ROOT, _INTERFACES:
        paths.update(root.glob(r'[a-z]*'))
        paths.update(root / i for i in include)
    return sorted(p.relative_to(_REPO_ROOT) for p in paths if (p / 'pyproject.toml').exists())


def _interfaces(include: list[str]) -> list[pathlib.Path]:
    paths = {*_INTERFACES.glob(r'[a-z]*'), *(_INTERFACES / i for i in include)}
    return sorted(p.relative_to(_REPO_ROOT) for p in paths if (p / 'interface').is_dir())


def _changed_only(
    dirs: list[pathlib.Path], old_ref: str, new_ref: str | None
) -> list[pathlib.Path]:
    cmd = ['git', 'diff', '--name-only', old_ref]
    if new_ref is not None:
        cmd.append(new_ref)
    names = subprocess.check_output(cmd, text=True).strip().splitlines()
    if new_ref is None:  # include untracked files when run w/out explicit new ref for local tests
        cmd = ['git', 'ls-files', '--others', '--exclude-standard']
        names.extend(subprocess.check_output(cmd, text=True).strip().splitlines())
    changes: set[pathlib.Path] = set()
    for name in names:
        parts = pathlib.Path(name).parts
        changes.add(pathlib.Path(parts[0]))
        changes.add(pathlib.Path(*parts[:2]))
    return [p for p in dirs if p in changes]


def _changed_version_only(
    dirs: list[pathlib.Path], old_ref: str, new_ref: str | None
) -> list[pathlib.Path]:
    with _snapshot_repo(old_ref) as root:
        old_versions = {p: _get_version(root, p) for p in dirs}
    with _snapshot_repo(new_ref) as root:
        new_versions = {p: _get_version(root, p) for p in dirs}
    packages_to_release: list[pathlib.Path] = []
    for p in dirs:
        old = old_versions[p]
        new = new_versions[p]
        if new is not None and '.dev' not in new and old != new:
            packages_to_release.append(p)
            logger.info('%s: %s -> %s', p, old, new)
    return packages_to_release


@contextlib.contextmanager
def _snapshot_repo(ref: str | None):
    if ref is None:
        yield _REPO_ROOT
        return
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        git = subprocess.run(['git', 'archive', ref], stdout=subprocess.PIPE, check=True)
        stream = io.BytesIO(git.stdout)
        with tarfile.open(fileobj=stream) as tar:
            tar.extractall(path=root)  # noqa: S202
        yield root


def _get_version(root: pathlib.Path, package: pathlib.Path | str) -> str | None:
    if not (root / package).exists():
        return None
    logger.debug('Computing version for %s', package)
    aliases = {
        # placeholders
        '.package': 'charmlibs',
        'interfaces/.package': 'charmlibs-interfaces',
        # examples
        '.example': 'charmlibs-example',
        'interfaces/.example': 'charmlibs-interfaces-example',
        '.tutorial': 'charmlibs-uptime',
    }
    dist_name = aliases.get(str(package), f'charmlibs-{package}'.replace('/', '-'))
    script = f'import importlib.metadata; print(importlib.metadata.version("{dist_name}"))'
    cmd = ['uv', 'run', '--no-project', '--with', f'./{package}', 'python', '-c', script]
    return subprocess.check_output(cmd, cwd=root, text=True).strip()


if __name__ == '__main__':
    print(json.dumps(_ls(_Args.from_cli())))
