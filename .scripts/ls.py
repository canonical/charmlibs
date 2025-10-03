#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.11"
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
import io
import json
import logging
import pathlib
import subprocess
import tarfile
import tempfile
import tomllib

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_INTERFACES = _REPO_ROOT / 'interfaces'

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


def _main() -> None:
    """Parse command-line arguments and output packages as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument('category', choices=('packages', 'interfaces'))
    parser.add_argument('old_ref', nargs='?')
    parser.add_argument('new_ref', nargs='?')
    parser.add_argument('--exclude-examples', action='store_true')
    parser.add_argument('--exclude-placeholders', action='store_true')
    parser.add_argument('--only-if-version-changed', action='store_true')
    args = parser.parse_args()
    result = _ls(
        category=args.category,
        refs=(args.old_ref, args.new_ref) if args.old_ref is not None else None,
        include_examples=not args.exclude_examples,
        include_placeholders=not args.exclude_placeholders,
        only_if_version_changed=args.only_if_version_changed,
    )
    print(json.dumps(result))


def _ls(
    category: str,
    refs: tuple[str, str | None] | None,
    only_if_version_changed: bool,
    include_examples: bool,
    include_placeholders: bool,
) -> list[str]:
    """Return directories matching the category and other options.

    Args:
        category: What to iterate over -- 'packages' or 'interfaces'.
        refs: Tuple of git references to diff with in the form `(old, new)`.
            If `new` is `None`, diff with the current state on disk.
            If provided, only changed items are returned.
        only_if_version_changed: Only output items that have had a version bump.
            Only respected if `refs` are provided.
            Not implemented for the 'packages' category.
        include_examples: Whether to include the example libraries.
            Typically included for testing, but excluded from docs and publishing.
        include_placeholders: Whether to include the namespace placeholder packages.
            Typically included for testing and publishing, but excluded from docs.

    Returns:
        A list of items from the specified category.
    """
    include: list[str] = []
    if include_examples:
        include.extend(('.example', '.tutorial'))
    if include_placeholders:
        include.append('.package')
    # Collect packages or interfaces.
    if category == 'packages':
        dirs = _packages(include=include)
    elif category == 'interfaces':
        dirs = _interfaces(include=include)
    else:
        raise ValueError(f'Unknown value for `category` {category!r}')
    # Filter based on changes.
    if refs:
        old_ref, new_ref = refs
        dirs = _changed_only(dirs, old_ref=old_ref, new_ref=new_ref)
        if only_if_version_changed and category == 'packages':
            dirs = _changed_version_only(dirs, old_ref=old_ref, new_ref=new_ref)
    return [str(p) for p in dirs]


def _packages(include: list[str]) -> list[pathlib.Path]:
    """Iterate over package directories in the repository.

    Returns any directory starting with [a-z] from the repository root and from the interfaces
    sub-directory, as well as any directories listed in `include`, if they exists and have a
    'pyproject.toml' file with a 'project' table.
    """
    paths: set[pathlib.Path] = set()
    for root in _REPO_ROOT, _INTERFACES:
        paths.update(root.glob(r'[a-z]*'))
        paths.update(root / i for i in include)
    return sorted(
        path.relative_to(_REPO_ROOT)
        for path in paths
        if (pyproject_toml := path / 'pyproject.toml').exists()
        and 'project' in tomllib.loads(pyproject_toml.read_text())
    )


def _interfaces(include: list[str]) -> list[pathlib.Path]:
    """Iterate over interface directories in the repository.

    Returns any directory starting with [a-z] from the interfaces sub-directory, as well as any
    directories listed in `include`, if they exist and have an 'interface' subdirectory.
    """
    paths = {*_INTERFACES.glob(r'[a-z]*'), *(_INTERFACES / i for i in include)}
    return sorted(p.relative_to(_REPO_ROOT) for p in paths if (p / 'interface').is_dir())


def _changed_only(
    dirs: list[pathlib.Path], old_ref: str, new_ref: str | None
) -> list[pathlib.Path]:
    """Return only those `dirs` that have changed between `old_ref` and `new_ref`.

    If `new_ref` is `None`, `git diff` is called with a single reference, and untracked files
    are included as changes. Calls `git diff` only once.
    """
    cmd = ['git', 'diff', '--name-only', old_ref]
    if new_ref is not None:
        cmd.append(new_ref)
    names = subprocess.check_output(cmd, text=True).strip().splitlines()
    # Include untracked files when run without explicit new ref (for local tests).
    if new_ref is None:
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
    """Returns only those `dirs` that have had a version change between `old_ref` and `new_ref`.

    Takes a snapshot of the repo for each reference.
    If `new_ref` is `None`, compares to the current working tree instead.
    Only implemented for Python package directories.
    Excludes changes where the new version is a dev version.
    """
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
            tar.extractall(path=root)  # noqa: S202
        yield root


def _get_version(root: pathlib.Path, package: pathlib.Path | str) -> str | None:
    """Return the version of `root / package`, or `None` if it doesn't exist."""
    if not (root / package).exists():
        return None
    logger.debug('Computing version for %s', package)
    with (root / package / 'pyproject.toml').open('rb') as f:
        dist_name = tomllib.load(f)['project']['name']
    script = f'import importlib.metadata; print(importlib.metadata.version("{dist_name}"))'
    cmd = ['uv', 'run', '--no-project', '--with', f'./{package}', 'python', '-c', script]
    return subprocess.check_output(cmd, cwd=root, text=True).strip()


if __name__ == '__main__':
    _main()
