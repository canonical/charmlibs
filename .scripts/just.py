#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ruff: noqa: I001  # tomllib is first-party in 3.11+

# Copyright 2026 Canonical Ltd.
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

"""Developer tooling for charmlibs; run `just` for quickstart info."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import tomllib
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import FunctionType
    from typing import IO

    _F = typing.TypeVar('_F', bound=FunctionType)

# `.scripts/just.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_REQUIREMENTS = REPO_ROOT / 'test-requirements.txt'

DEFAULT_PYTHON = '3.10'

# ANSI escape codes for formatting the messages.
BOLD = '\033[1m'
NORMAL = '\033[0m'
CYAN = '\033[36m'
# Quick start message printed when called with no arguments.
QUICK_START = f"""
{BOLD}Charmlibs is Canonical's charm library monorepo{NORMAL}

{BOLD}List all commands with {CYAN}just help{NORMAL}{BOLD}, or:{NORMAL}
- Create a new package: {CYAN}just init{NORMAL} or {CYAN}just init --interface{NORMAL}
- Add a dependency to a package: {CYAN}just add <package> <dependency>{NORMAL}
- Lint, unit test, and build docs for a package: {CYAN}just check <package>{NORMAL}
- Run {CYAN}ruff{NORMAL} for all packages: {CYAN}just fast-lint{NORMAL}

{BOLD}Run individual checks for a package:{NORMAL}
- {CYAN}just lint <package>{NORMAL} (fix errors with {CYAN}just format <package>{NORMAL})
- {CYAN}just unit <package>{NORMAL}
- {CYAN}just functional <package>{NORMAL} (may require extra software like {CYAN}pebble{NORMAL})

{BOLD}Run integration tests{NORMAL} (requires a Juju controller and a cloud):
- Pack: {CYAN}just pack-k8s <package>{NORMAL} or {CYAN}just pack-machine <package>{NORMAL}
- Run: {CYAN}just integration-k8s <package>{NORMAL} or {CYAN}just integration-machine{NORMAL}

{BOLD}Build the docs: {CYAN}just docs{NORMAL}
- For specific packages only: {CYAN}just docs html <packages>{NORMAL}
""".strip()

# Mapping of recipe names to their functions, populated by the `_register` decorator.
# `just help` prints the recipes in registration order.
RECIPES: dict[str, Callable[[list[str]], int]] = {}


def _register(fn: _F) -> _F:
    RECIPES[fn.__name__.removeprefix('_').replace('_', '-')] = fn
    return fn


def main(argv: list[str]) -> int:
    """Dispatch `argv` to the named recipe, returning its exit code."""
    if not argv or argv[0] in ('-h', '--help'):
        print(QUICK_START)
        return 0
    name, *args = argv
    func = RECIPES.get(name)
    if func is None:
        print(f'Unknown recipe: {name!r}\n', file=sys.stderr)
        print(QUICK_START)
        return 2
    return func(args)


@_register
def help(argv: list[str]) -> int:  # noqa: A001
    """Describe usage and list the available recipes."""
    _parser(help).parse_args(argv)
    print('All recipes require `uv` to be available.\n')
    print('Available recipes:')
    width = max(len(name) for name in RECIPES)
    for name, func in RECIPES.items():
        if func.__name__.startswith('_'):
            continue  # Skip private recipes.
        summary = (func.__doc__ or '').splitlines()[0] if func.__doc__ else ''
        print(f'    {name:<{width}}  {summary}')
    return 0


@_register
def init(argv: list[str]) -> int:
    """Scaffold a new charmlibs package interactively (forwards extra args to cookiecutter)."""
    parser = _parser(init)
    parser.add_argument(
        '--interface',
        action='store_true',
        help='Scaffold a charmlibs.interfaces package instead of a general charmlibs package.',
    )
    args, cookiecutter_args = parser.parse_known_args(argv)
    if args.interface:
        print(
            f'✨{BOLD}IMPORTANT{NORMAL}✨ The project name should be the canonical interface'
            f' name, as used in {CYAN}charmcraft.yaml{NORMAL} files.'
        )
    else:
        print(
            f'✨{BOLD}IMPORTANT{NORMAL}✨ The project name should be the import package name,'
            f' without the {CYAN}charmlibs.{NORMAL} namespace.'
        )
    print('You can press enter to accept the default, shown in brackets.')
    template = REPO_ROOT / '.template'
    cmd = ['uvx', 'cookiecutter']
    if args.interface:
        cmd.extend(['--output-dir', 'interfaces'])
    cmd.append(template.name)
    if args.interface:
        cmd.append('_interface=True')
    cmd.extend(cookiecutter_args)
    _run(cmd, env={**os.environ, 'CHARMLIBS_TEMPLATE': str(template.resolve())})
    return 0


@_register
def add(argv: list[str]) -> int:
    """Run `uv add` for a package, respecting repo-level version constraints.

    Example: `add pathops 'pydantic>=2'` adds a constrained dependency to pathops.
    """
    parser = _parser(add)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, uv_args = parser.parse_known_args(argv)
    cmd = ['uv', 'add', '--constraints', TEST_REQUIREMENTS, *uv_args]
    _run(cmd, cwd=REPO_ROOT / args.package)
    return 0


@_register
def check(argv: list[str]) -> int:
    """`lint`, `unit` test, and build the `docs` for a package."""
    args = _package_parser(check).parse_args(argv)
    python = _resolve_python(args.package, args.python)
    if failures := lint([args.package, '--python', python]):
        sys.exit(failures)
    for cmd in _coverage_cmds(REPO_ROOT / args.package, 'unit', python, ['-rA']):
        _run(cmd, cwd=REPO_ROOT / args.package, env=_coverage_env())
    _run(['just', 'docs', 'html', args.package])
    return 0


@_register
def format(argv: list[str]) -> int:  # noqa: A001
    """Run `ruff check --fix` and `ruff format`, modifying files in place."""
    parser = _parser(format)
    parser.add_argument(
        'path', nargs='?', default='.', help='Path to format, defaults to the repo.'
    )
    parser.add_argument(
        '--unsafe-fixes',
        action='store_true',
        help='Forward `--unsafe-fixes` to `ruff check`, applying fixes marked as unsafe.',
    )
    args = parser.parse_args(argv)
    ruff = ['uv', 'run', '--only-group=fast-lint', 'ruff']
    _run([*ruff, 'format', args.path])
    check = [*ruff, 'check', '--fix']
    if args.unsafe_fixes:
        check.append('--unsafe-fixes')
    _run([*check, args.path])
    return 0


# --- Linting recipes ---------------------------------------------------------------------------


@_register
def lint(argv: list[str]) -> int:
    """Run fast linting (`ruff`) and static analysis (`pyright`) for a package."""
    args, pyright_args = _package_parser(lint).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    failures = _fast_lint(args.package)
    if _static(args.package, python, pyright_args) != 0:
        failures += 1
    return failures


@_register
def fast_lint(argv: list[str]) -> int:
    """Run `ruff`, failing afterwards if any errors are found."""
    parser = _parser(fast_lint)
    parser.add_argument('path', nargs='?', default='.', help='Path to lint, defaults to the repo.')
    args = parser.parse_args(argv)
    return _fast_lint(args.path)


@_register
def static(argv: list[str]) -> int:
    """Run `pyright` static analysis for a package."""
    args, pyright_args = _package_parser(static).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    return _static(args.package, python, pyright_args)


def _fast_lint(path: str) -> int:
    """Run `ruff check` and `ruff format --diff`, returning the number of failing commands.

    The `ruff check --diff` output (the fixes that would resolve `ruff check` issues) is printed
    for information, but never counts as a failure.
    """
    ruff = ['uv', 'run', '--only-group=fast-lint', 'ruff']
    failures = 0
    if _run([*ruff, 'check', path], check=False) != 0:
        _run([*ruff, 'check', '--diff', path], check=False)
        failures += 1
    if _run([*ruff, 'format', '--diff', path], check=False) != 0:
        failures += 1
    return failures


def _static(package: str, python: str, pyright_args: Sequence[str]) -> int:
    """Run `pyright` for a package against the given Python version, returning its exit code."""
    pkg_dir = REPO_ROOT / package
    cmd = ['--with', 'pytest-interface-tester'] if pkg_dir.parent.name == 'interfaces' else []
    cmd.extend(['pyright', f'--pythonversion={python}', *pyright_args])
    groups = ['lint', 'unit', 'functional', 'integration']
    return _uv_run(cmd, pkg_dir=pkg_dir, python=python, groups=groups, check=False)


# --- Coverage recipes ---------------------------------------------------------------------------


@_register
def unit(argv: list[str]) -> int:
    """Run unit tests with `coverage` for a package."""
    args, pytest_args = _package_parser(unit).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    cmds = _coverage_cmds(REPO_ROOT / args.package, 'unit', python, pytest_args or ['-rA'])
    for cmd in cmds:
        _run(cmd, cwd=REPO_ROOT / args.package, env=_coverage_env())
    return 0


@_register
def functional(argv: list[str]) -> int:
    """Run functional tests with `coverage` for a package."""
    args, pytest_args = _package_parser(functional).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    cmds = _coverage_cmds(REPO_ROOT / args.package, 'functional', python, pytest_args or ['-rA'])
    joined = ' && '.join(shlex.join(str(part) for part in cmd) for cmd in cmds)
    script = textwrap.dedent(
        f"""
        set -xueo pipefail
        if [ -e tests/functional/setup.sh ]; then
            source ./tests/functional/setup.sh
        fi
        set +e  # Allow the command to fail.
        {joined}
        returncode=$?
        set -e  # Exit on error again.
        if [ -e tests/functional/teardown.sh ]; then
            source ./tests/functional/teardown.sh
        fi
        exit "$returncode"
        """
    ).strip()
    _run(['bash', '-c', script], cwd=REPO_ROOT / args.package, env=_coverage_env())
    return 0


def _coverage_cmds(pkg_dir: pathlib.Path, suite: str, python: str, pytest_args: list[str]):
    """Return cmds for `coverage run -m pytest` and `coverage report` for package and suite."""
    data_file_arg = f'--data-file=.report/coverage-{suite}-{python}.db'
    run = [
        *('coverage', 'run', data_file_arg, '--source=src', '-m'),
        *('pytest', '--tb=native', '-vv', f'tests/{suite}', *pytest_args),
    ]
    run_cmd = _uv_cmd(run, pkg_dir=pkg_dir, python=python, groups=[suite])
    report = ['coverage', 'report', data_file_arg]
    report_cmd = _uv_cmd(report, pkg_dir=pkg_dir, python=python, groups=[suite])
    return run_cmd, report_cmd


@_register
def combine_coverage(argv: list[str]) -> int:
    """Combine a package's `coverage` reports."""
    args = _package_parser(combine_coverage).parse_args(argv)
    pkg_dir = REPO_ROOT / args.package
    python = _resolve_python(args.package, args.python)
    env = _coverage_env()
    data_files: list[str] = []
    for test_id in 'unit', 'functional':
        file = f'.report/coverage-{test_id}-{python}.db'
        if (pkg_dir / file).exists():
            data_files.append(file)

    def uv(cmd: list[str]) -> None:
        _uv_run(cmd, pkg_dir=pkg_dir, python=python, env=env)

    # Combine reports and generate XML.
    data_file_arg = f'--data-file=.report/coverage-all-{python}.db'
    uv(['coverage', 'combine', '--keep', data_file_arg, *data_files])
    uv(['coverage', 'xml', data_file_arg, '-o', f'.report/coverage-all-{python}.xml'])
    # Rebuild the HTML report from scratch (let coverage recreate the directory).
    html_dir = f'.report/htmlcov-all-{python}'
    shutil.rmtree(pkg_dir / html_dir, ignore_errors=True)
    uv(['coverage', 'html', data_file_arg, '--show-contexts', f'--directory={html_dir}'])
    # Print the report last.
    uv(['coverage', 'report', data_file_arg])
    return 0


def _coverage_env() -> dict[str, str]:
    """Return the environment with `COVERAGE_RCFILE` pointing at the repo `pyproject.toml`."""
    return {**os.environ, 'COVERAGE_RCFILE': str(REPO_ROOT / 'pyproject.toml')}


# --- Pack recipes ------------------------------------------------------------------------------


@_register
def pack_k8s(argv: list[str]) -> int:
    """Pack Kubernetes charm(s) for a package's Juju integration tests."""
    return _pack(pack_k8s, 'k8s', argv)


@_register
def pack_machine(argv: list[str]) -> int:
    """Pack machine charm(s) for a package's Juju integration tests."""
    return _pack(pack_machine, 'machine', argv)


def _pack(fn: FunctionType, substrate: str, argv: list[str]) -> int:
    """Pack the package's integration-test charm(s) for the given substrate."""
    parser = _parser(fn)
    parser.add_argument(
        '--tag',
        default=os.environ.get('CHARMLIBS_TAG', ''),
        help='Value for the CHARMLIBS_TAG environment var (defaults to $CHARMLIBS_TAG).',
    )
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pack_args = parser.parse_known_args(argv)
    integration_dir = REPO_ROOT / args.package / 'tests' / 'integration'
    env = {**os.environ, 'CHARMLIBS_SUBSTRATE': substrate, 'CHARMLIBS_TAG': args.tag}
    return _run(['./pack.sh', *pack_args], cwd=integration_dir, env=env)


# --- Integration recipes ------------------------------------------------------------------------


@_register
def integration_k8s(argv: list[str]) -> int:
    """Run a package's Kubernetes Juju integration tests."""
    return _integration(integration_k8s, 'k8s', argv)


@_register
def integration_machine(argv: list[str]) -> int:
    """Run a package's machine Juju integration tests."""
    return _integration(integration_machine, 'machine', argv)


def _integration(fn: FunctionType, substrate: str, argv: list[str]) -> int:
    """Run the package's Juju integration tests for the given substrate."""
    parser = _package_parser(fn)
    parser.add_argument(
        '--tag',
        default=os.environ.get('CHARMLIBS_TAG', ''),
        help='Value for the CHARMLIBS_TAG environment var (defaults to $CHARMLIBS_TAG).',
    )
    args, pytest_args = parser.parse_known_args(argv)
    return _uv_run(
        [
            *('pytest', '--tb=native', '-vv'),
            *('-m', {'k8s': 'not machine_only', 'machine': 'not k8s_only'}[substrate]),
            'tests/integration',
            *(pytest_args or ['-rA']),
        ],
        pkg_dir=REPO_ROOT / args.package,
        python=_resolve_python(args.package, args.python),
        groups=['integration'],
        env={**os.environ, 'CHARMLIBS_SUBSTRATE': substrate, 'CHARMLIBS_TAG': args.tag},
    )


# --- Other recipes -----------------------------------------------------------------------------


@_register
def interfaces_json(argv: list[str]) -> int:
    """Generate `interfaces/index.json` from the interface libraries."""
    _parser(interfaces_json).parse_args(argv)  # supports `-h`
    outputs = [
        'name',
        'version',
        'lib',
        'lib_url',
        'docs_url',
        'summary',
        'description',
        'tags',
        'status',
    ]
    cmd: list[str | pathlib.Path] = ['.scripts/ls.py', 'interfaces', '--indent-json']
    for output in outputs:
        cmd.extend(['--output', output])
    with (REPO_ROOT / 'interfaces' / 'index.json').open('w') as f:
        _run(cmd, stdout=f)
    return 0


@_register
def _scripts_unit(argv: list[str]) -> int:
    """Run the unit tests for the repository tooling in `.scripts/`."""
    _parser(_scripts_unit).parse_args(argv)
    _run([
        *('uv', 'run', '--with-requirements', TEST_REQUIREMENTS, '--python', '3.12'),
        *('pytest', '--tb=native', '-vv', '.scripts/tests', *(argv or ['-rA'])),
    ])
    return 0


@_register
def _scripts_static(argv: list[str]) -> int:
    """Run `pyright` static analysis for the repository tooling in `.scripts/`."""
    _parser(_scripts_static).parse_args(argv)
    cmd = [
        'uv',
        'run',
        '--no-project',
        f'--with-requirements={TEST_REQUIREMENTS}',
        '--with=pyyaml',
        '--python=3.12',
        'pyright',
    ]
    _run(cmd, cwd=REPO_ROOT / '.scripts')
    return 0


# --- Parser ------------------------------------------------------------------------------------


def _parser(fn: FunctionType) -> argparse.ArgumentParser:
    """Return an `ArgumentParser` for recipe `fn`, deriving prog and description from it."""
    prog = f'just {fn.__name__.replace("_", "-")}'
    return argparse.ArgumentParser(prog=prog, description=fn.__doc__)


def _package_parser(fn: FunctionType) -> argparse.ArgumentParser:
    """Return an `ArgumentParser` with the common `--python` and `package` arguments."""
    parser = _parser(fn)
    parser.add_argument(
        '--python',
        default=None,
        help="Python version to use, e.g. `3.12` (defaults to the package's minimum).",
    )
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    return parser


# --- Resolve Python version --------------------------------------------------------------------


def _resolve_python(package: str, python: str | None) -> str:
    """Return the Python version to test `package` with.

    If `python` is `None`, return the higher of `DEFAULT_PYTHON`
    and the package's minimum Python version.
    """
    if python:
        return python
    minimum = _requires_python_minimum(REPO_ROOT / package)
    return max(DEFAULT_PYTHON, minimum, key=lambda s: tuple(int(p) for p in s.split('.')))


def _requires_python_minimum(pkg_dir: pathlib.Path) -> str:
    """Return the `major.minor` lower bound of `pkg_dir`'s `requires-python`, e.g. `'3.14159'`."""
    pyproject_toml = tomllib.loads((pkg_dir / 'pyproject.toml').read_text())
    requires_python = pyproject_toml['project']['requires-python']
    regex = (
        r'(?:>=|~=)'  # a `>=` or `~=` operator: the ones that set a lower bound
        r'\s*'  # optional whitespace between the operator and the version
        r'(\d+\.\d+)'  # capture just `major.minor`, stopping before any patch component
    )
    match = re.search(regex, requires_python)
    if match is None:
        raise ValueError(f"Couldn't find minimum version in requires-python: {requires_python!r}")
    return match.group(1)


# --- uv run ------------------------------------------------------------------------------------


def _uv_run(
    args: Sequence[str | pathlib.Path],
    *,
    pkg_dir: pathlib.Path,
    python: str,
    groups: Sequence[str] = (),
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    """Run `uv run ... <args>` in `pkg_dir`, returning the exit code."""
    cmd = _uv_cmd(args, pkg_dir=pkg_dir, python=python, groups=groups)
    return _run(cmd, cwd=pkg_dir, env=env, check=check, stdout=stdout)


def _run(
    cmd: Sequence[str | pathlib.Path],
    *,
    cwd: pathlib.Path = REPO_ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    """Echo and run a command, returning its exit code."""
    env = dict(os.environ if env is None else env)
    env.pop('VIRTUAL_ENV', None)  # Don't propagate script's ephemeral venv.
    print([str(part) for part in cmd], file=sys.stderr, flush=True)
    returncode = subprocess.call(cmd, cwd=cwd, env=env, stdout=stdout)
    if check and returncode != 0:
        sys.exit(returncode)
    return returncode


def _uv_cmd(
    args: Sequence[str | pathlib.Path],
    *,
    pkg_dir: pathlib.Path,
    python: str,
    groups: Sequence[str] = (),
) -> list[str | pathlib.Path]:
    """Build a `uv run ... <args>` command list to be executed in `pkg_dir`."""
    cmd = ['uv', 'run', '--with-requirements', TEST_REQUIREMENTS, '--python', python]
    if (pkg_dir / 'uv.lock').exists():
        cmd.append('--locked')
    available = _dependency_groups(pkg_dir)
    for group in groups:
        if group in available:
            cmd.extend(['--group', group])
    return [*cmd, *args]


def _dependency_groups(pkg_dir: pathlib.Path) -> set[str]:
    """Return the PEP 735 dependency group names declared in `pyproject.toml`."""
    pyproject_toml = tomllib.loads((pkg_dir / 'pyproject.toml').read_text())
    return set(pyproject_toml.get('dependency-groups', ()))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
