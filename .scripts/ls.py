#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "PyYAML",
# ]
# ///

# ruff: noqa: I001  # tomllib is first-party in 3.11+

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

"""Output the packages or interfaces in the repository as a JSON list.

See the the command-line help for options.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import dataclasses
import functools
import io
import json
import logging
import pathlib
import re
import subprocess
import tarfile
import tempfile
import tomllib

import yaml

_REPO_ROOT = pathlib.Path(__file__).parent.parent

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


@dataclasses.dataclass(kw_only=True)
class Info:
    """Information about a specific package or interface."""

    path: str
    name: str = ''
    version: str = ''
    lib: str = ''
    lib_url: str = ''
    docs_url: str = ''
    summary: str = ''
    description: str = ''
    status: str = ''

    def to_dict(self, *fields: str) -> dict[str, str]:
        """Return dictionary containing only specified fields."""
        return {field: getattr(self, field) for field in fields}


def _main() -> None:
    """Parse command-line arguments and output packages as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument('category', choices=('packages', 'interfaces'))
    parser.add_argument('old_ref', nargs='?')
    parser.add_argument('new_ref', nargs='?')
    parser.add_argument('--exclude-examples', action='store_true')
    parser.add_argument('--exclude-placeholders', action='store_true')
    parser.add_argument('--only-if-version-changed', action='store_true')
    parser.add_argument('--indent-json', action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--output', action='append', choices=[f.name for f in dataclasses.fields(Info)]
    )
    group.add_argument('--name-only', action='store_true')
    args = parser.parse_args()
    single_output = 'name' if args.name_only else 'path'  # used if --output isn't specified
    infos = _ls(
        category=args.category,
        old_ref=args.old_ref,
        new_ref=args.new_ref,
        include_examples=not args.exclude_examples,
        include_placeholders=not args.exclude_placeholders,
        only_if_version_changed=args.only_if_version_changed,
        output=args.output or [single_output],
    )
    if args.output:
        result = sorted(
            (info.to_dict(*args.output) for info in infos),
            key=lambda di: tuple(di.items()),
        )
    else:
        result = sorted(getattr(info, single_output) for info in infos)
    print(json.dumps(result, indent=2 if args.indent_json else None))


def _ls(
    category: str,
    old_ref: str | None,
    new_ref: str | None,
    only_if_version_changed: bool,
    include_examples: bool,
    include_placeholders: bool,
    output: list[str],
) -> list[Info]:
    """Return info about directories matching the category, filtered based on the other options.

    Args:
        category: What to iterate over -- 'packages' or 'interfaces'.
        old_ref: git reference to diff with.
            If `None`, no diff is performed.
            Otherwise only changed items are returned.
        new_ref: if old_ref is not `None`, diff it with new_ref.
            If this new_ref is `None`, old_ref is diffed with the current state on disk.
        only_if_version_changed: Only output items that have had a version bump.
            Only respected if `refs` are provided.
        include_examples: Whether to include the example libraries.
            Typically included for testing, but excluded from docs and publishing.
        include_placeholders: Whether to include the namespace placeholder packages.
            Typically included for testing and publishing, but excluded from docs.
        output: List of fields to include in the output, one or more of
            'name', 'path', or 'version'
    """
    include: list[str] = []
    if include_examples:
        include.extend(('.example', '.tutorial'))
    if include_placeholders:
        include.append('.package')
    with _snapshot_repo(new_ref) as root:
        # Collect packages or interfaces.
        if category == 'packages':
            dirs = _packages(root, include=include)
        elif category == 'interfaces':
            dirs = _interfaces(root, include=include)
        else:
            raise ValueError(f'Unknown value for `category` {category!r}')
        # Filter based on changes.
        # Return full info if we calculate it.
        if old_ref:
            dirs = _changed_only(root, dirs, ref=old_ref)
            if only_if_version_changed:
                dirs = _get_changed_versions_only(category, root, dirs, ref=old_ref)
        # Calculate only the information needed.
        infos: list[Info] = []
        for path in dirs:
            info = Info(path=str(path))
            if 'name' in output:
                info.name = _get_name(category, root, path)
            if 'version' in output:
                info.version = _get_version(category, root, path)
            if 'summary' in output:
                info.summary = _get_summary(category, root, path)
            if 'description' in output:
                info.description = _get_description(category, root, path)
            if 'lib' in output:
                info.lib = _get_lib_name(category, root, path)
            if 'lib_url' in output:
                info.lib_url = _lib_urls().get(_get_lib_name(category, root, path), '')
            if 'docs_url' in output:
                info.docs_url = _get_docs_url(category, root, path)
            if 'status' in output:
                info.status = _get_status(category, root, path)
            infos.append(info)
        return infos


def _packages(root: pathlib.Path, include: list[str]) -> list[pathlib.Path]:
    """Iterate over package directories in the repository.

    Returns any directory starting with [a-z] from the root and from the 'interfaces'
    sub-directory, as well as any directories listed in `include`, if they exists and have a
    'pyproject.toml' file with a 'project' table.
    """
    paths: set[pathlib.Path] = set()
    for r in root, root / 'interfaces':
        paths.update(r.glob(r'[a-z]*'))
        paths.update(r / i for i in include)
    return sorted(path.relative_to(root) for path in paths if _is_package(path))


def _is_package(path: pathlib.Path) -> bool:
    """Return whether path points to a Python package."""
    pyproject_toml = path / 'pyproject.toml'
    if not pyproject_toml.exists():
        return False
    return 'project' in tomllib.loads(pyproject_toml.read_text())


def _interfaces(root: pathlib.Path, include: list[str]) -> list[pathlib.Path]:
    """Iterate over interface directories in the repository.

    Returns any directory starting with [a-z] from the interfaces sub-directory, as well as any
    directories listed in `include`, if they exist and have an 'interface' subdirectory.
    """
    interfaces_root = root / 'interfaces'
    paths: set[pathlib.Path] = {*interfaces_root.glob(r'[a-z]*')}
    paths.update(interfaces_root / path for path in include)
    return sorted(path.relative_to(root) for path in paths if _is_interface(path))


def _is_interface(path: pathlib.Path) -> bool:
    """Return whether path points to a directory containing an interface definition."""
    return (path / 'interface').is_dir()


def _changed_only(root: pathlib.Path, dirs: list[pathlib.Path], ref: str) -> list[pathlib.Path]:
    """Return only those `dirs` that have changed between `ref` and current state on disk.

    Untracked files are included as changes.
    Calls `git diff` and `git ls-files` once each.
    """
    cmd = ['git', 'diff', '--name-only', ref]
    names = subprocess.check_output(cmd, text=True).strip().splitlines()
    # Include untracked files (for running locally).
    cmd = ['git', 'ls-files', '--others', '--exclude-standard']
    names.extend(subprocess.check_output(cmd, text=True).strip().splitlines())
    # Make set of all top-level and one-level-deep parents of changes.
    # e.g. [foo/bar/baz/bartholemew] -> {foo, foo/bar}
    changes: set[pathlib.Path] = set()
    for name in names:
        parts = pathlib.Path(name).parts
        changes.add(pathlib.Path(parts[0]))
        changes.add(pathlib.Path(*parts[:2]))
    return [p for p in dirs if p in changes]


def _get_changed_versions_only(
    category: str, root: pathlib.Path, dirs: list[pathlib.Path], ref: str
) -> list[pathlib.Path]:
    """Returns only those packages that have had a version change between `ref` and current state.

    Takes a snapshot of the repo at `ref` for comparison.
    Excludes changes where the new version is a dev version.
    """
    with _snapshot_repo(ref) as old_root:
        old_versions: dict[str, str] = {}
        for path in dirs:
            try:
                name = _get_name(category, old_root, path)
            except FileNotFoundError:
                continue
            version = _get_version(category, old_root, path)
            old_versions[name] = version
    changed: list[pathlib.Path] = []
    for path in dirs:
        if not (root / path).exists():
            logger.debug('%s no longer exists!', path)
            continue
        name = _get_name(category, root, path)
        old_version = old_versions.get(name)
        new_version = _get_version(category, root, path)
        logger.info('%s (%s): %s -> %s', path, name, old_version, new_version)
        if new_version == old_version:
            logger.debug('Version unchanged')
        elif 'dev' in new_version:
            logger.debug('Skipping dev release.')
        else:
            changed.append(path)
    return changed


@contextlib.contextmanager
def _snapshot_repo(ref: str | None):
    """Yield a snapshot of the current repository at the specified reference in a temp dir.

    If `ref` is `None`, yield the current repository root instead.
    """
    if ref is None:
        yield _REPO_ROOT
        return
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        git = subprocess.run(['git', 'archive', ref], stdout=subprocess.PIPE, check=True)
        stream = io.BytesIO(git.stdout)
        with tarfile.open(fileobj=stream) as tar:
            tar.extractall(path=root, filter='data')
        yield root


def _get_name(category: str, root: pathlib.Path, path: pathlib.Path) -> str:
    """Return package or interface name."""
    if category == 'packages':
        return _get_dist_name(path, root=root)
    assert category == 'interfaces'
    return path.name


def _get_version(category: str, root: pathlib.Path, path: pathlib.Path) -> str:
    if category == 'packages':
        return _get_package_version(path, root=root)
    assert category == 'interfaces'
    return _get_interface_version(path, root=root)


def _get_summary(category: str, root: pathlib.Path, path: pathlib.Path) -> str:
    if category == 'packages':
        return _get_description(category, root, path)
    assert category == 'interfaces'
    return _interface_yaml(path, root=root).get('summary', '').strip()


def _get_description(category: str, root: pathlib.Path, path: pathlib.Path) -> str:
    if category == 'packages':
        return _pyproject_toml(path, root=root)['project']['description'].strip()
    assert category == 'interfaces'
    return _interface_yaml(path, root=root).get('description', '').strip()


def _get_lib_name(category: str, root: pathlib.Path, path: pathlib.Path) -> str:
    if category == 'packages':
        if path.name == '.package':
            # .package -> () -> 'charmlibs'
            # interfaces/.package -> ('interfaces') -> 'charmlibs.interface'
            parts, _ = path.parts
        else:
            # For special cases like '.tutorial' -> ('tutorial') -> 'charmlibs.tutorial'
            parts = tuple(p.removeprefix('.') for p in path.parts)
        return '.'.join(('charmlibs', *parts)).replace('-', '_')
    assert category == 'interfaces'
    return _interface_yaml(path, root=root).get('lib', '').strip()


def _get_docs_url(category: str, root: pathlib.Path, path: pathlib.Path) -> str:
    if category == 'packages':
        url = _pyproject_toml(path, root=root)['project']['urls'].get('Documentation', '')
        return url.strip()
    assert category == 'interfaces'
    return f'https://documentation.ubuntu.com/charmlibs/reference/interfaces/{path.name}/'


def _get_status(category: str, root: pathlib.Path, path: pathlib.Path) -> str:
    if category == 'packages':
        return ''
    assert category == 'interfaces'
    return _interface_yaml(path, root=root).get('status', '').strip()


def _get_dist_name(package: pathlib.Path, root: pathlib.Path = _REPO_ROOT) -> str:
    """Load distribution package name from pyproject.toml and normalize it."""
    name = _pyproject_toml(package, root=root)['project']['name']
    return _normalize(name.strip())


@functools.cache
def _get_package_version(package: pathlib.Path, root: pathlib.Path = _REPO_ROOT) -> str:
    name = _get_dist_name(package, root=root)
    script = f'import importlib.metadata; print(importlib.metadata.version("{name}"))'
    cmd = ['uv', 'run', '--no-project', '--with', root / package, 'python', '-c', script]
    return subprocess.check_output(cmd, cwd=root, text=True).strip()


@functools.cache
def _get_interface_version(path: pathlib.Path, root: pathlib.Path = _REPO_ROOT) -> str:
    versions = [v.name for v in (root / path / 'interface').glob('v[0-9]*')]
    return max((v.removeprefix('v') for v in versions), key=int)


@functools.cache
def _lib_urls() -> dict[str, str]:
    result: dict[str, str] = {}
    for p in 'general-libs.csv', 'interface-libs.csv':
        with (_REPO_ROOT / '.docs' / 'reference' / p).open() as f:
            for row in csv.DictReader(f):
                # Library names should be unique, but we currently have an entry for
                # charms.data_platform_libs.data_interfaces for each interface it supports
                # This doesn't break our lookups though, since they all have the same metadata
                # (aside from the interface column)
                assert (
                    row['name'] not in result
                    or row['name'] == 'charms.data_platform_libs.data_interfaces'
                )
                result[row['name']] = row['url']
    return result


@functools.cache
def _pyproject_toml(package: pathlib.Path, root: pathlib.Path = _REPO_ROOT):
    with (root / package / 'pyproject.toml').open('rb') as f:
        return tomllib.load(f)


@functools.cache
def _interface_yaml(path: pathlib.Path, root: pathlib.Path = _REPO_ROOT):
    version = _get_interface_version(path, root=root)
    with (root / path / 'interface' / f'v{version}' / 'interface.yaml').open() as f:
        return yaml.safe_load(f)


def _normalize(name: str) -> str:
    """Normalize distribution package name according to PyPI rules.

    https://packaging.python.org/en/latest/specifications/name-normalization/#name-normalization
    """
    return re.sub(r'[-_.]+', '-', name).lower()


if __name__ == '__main__':
    _main()
