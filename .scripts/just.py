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
import contextlib
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from types import FunctionType
    from typing import IO

    _F = typing.TypeVar('_F', bound=FunctionType)

# `.scripts/just.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_REQUIREMENTS = REPO_ROOT / 'test-requirements.txt'
# The default Python version to use, and the minimum we'll run with.
DEFAULT_PYTHON = '3.10'


class Colors:
    """ANSI escape codes for formatting messages, empty strings when color is disabled."""

    def __init__(self) -> None:
        if self._enabled():
            self.bold = '\033[1m'
            self.normal = '\033[0m'
            self.cyan = '\033[36m'
        else:
            self.bold = self.normal = self.cyan = ''

    @staticmethod
    def _enabled() -> bool:
        """Return whether to emit ANSI color codes."""
        if (force := os.environ.get('FORCE_COLOR')) and force != '0':
            return True
        if (no := os.environ.get('NO_COLOR')) and no != '0':
            return False
        return sys.stdout.isatty()


# --- Main --------------------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """Dispatch `argv` to the named recipe, returning its exit code."""
    if not argv or argv[0] in ('-h', '--help'):
        print(_quick_start())
        return 0
    name, *args = argv
    func = RECIPES.get(name)
    if func is None:
        print(f'Unknown recipe: {name!r}\n', file=sys.stderr)
        print(_quick_start())
        return 2
    return func(args)


def _quick_start() -> str:
    c = Colors()
    return f"""
{c.bold}Charmlibs is Canonical's charm library monorepo{c.normal}

{c.bold}List all commands with {c.cyan}just help{c.normal}{c.bold}, or:{c.normal}
- Create a new package: {c.cyan}just init{c.normal} or {c.cyan}just init --interface{c.normal}
- Add a dependency to a package: {c.cyan}just add <package> <dependency>{c.normal}
- Lint, unit test, and build docs for a package: {c.cyan}just check <package>{c.normal}
- Run {c.cyan}ruff{c.normal} for all packages: {c.cyan}just fast-lint{c.normal}

{c.bold}Run individual checks for a package:{c.normal}
- {c.cyan}just lint <package>{c.normal} (fix errors with {c.cyan}just format <package>{c.normal})
- {c.cyan}just unit <package>{c.normal}
- {c.cyan}just functional <package>{c.normal} (may need sudo and additional software installed)

{c.bold}Run integration tests{c.normal} (requires a Juju controller and a cloud):
- Pack: {c.cyan}just pack-k8s <package>{c.normal} or {c.cyan}just pack-machine <package>{c.normal}
- Run (excluding machine_only tests): {c.cyan}just integration-k8s <package>{c.normal}
- Run (excluding k8s_only tests): {c.cyan}just integration-machine <package>{c.normal}

{c.bold}Build the docs: {c.cyan}just docs{c.normal}
- For specific packages only: {c.cyan}just docs html <packages>{c.normal}
""".strip()


# --- Recipes -----------------------------------------------------------------------------------

# Mapping of recipe names to their functions, populated by the `_register` decorator.
# `just help` prints the recipes in registration order.
RECIPES: dict[str, Callable[[list[str]], int]] = {}


def _register(fn: _F) -> _F:
    RECIPES[fn.__name__.removeprefix('_').replace('_', '-')] = fn
    return fn


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
    c = Colors()
    if args.interface:
        print(
            f'✨{c.bold}IMPORTANT{c.normal}✨ The project name should be the canonical interface'
            f' name, as used in {c.cyan}charmcraft.yaml{c.normal} files.'
        )
    else:
        print(
            f'✨{c.bold}IMPORTANT{c.normal}✨ The project name should be the import package name,'
            f' without the {c.cyan}charmlibs.{c.normal} namespace.'
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
    package_argv = [args.package, '--python', python]
    if args.resolution is not None:
        package_argv.extend(['--resolution', args.resolution])
    if failures := lint(package_argv):
        sys.exit(failures)
    unit(package_argv)
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
    if _static(args.package, python, pyright_args, resolution=args.resolution) != 0:
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
    return _static(args.package, python, pyright_args, resolution=args.resolution)


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


def _static(
    package: str,
    python: str,
    pyright_args: Sequence[str],
    *,
    resolution: str | None = None,
) -> int:
    """Run `pyright` for a package against the given Python version, returning its exit code."""
    pkg_dir = REPO_ROOT / package
    cmd = ['--with', 'pytest-interface-tester'] if pkg_dir.parent.name == 'interfaces' else []
    cmd.extend(['pyright', f'--pythonversion={python}', *pyright_args])
    groups = ['lint', 'unit', 'functional', 'integration']
    with _resolution_sandbox(pkg_dir, resolution):
        return _uv_run(
            cmd, pkg_dir=pkg_dir, python=python, groups=groups, resolution=resolution, check=False
        )


# --- Coverage recipes ---------------------------------------------------------------------------


@_register
def unit(argv: list[str]) -> int:
    """Run unit tests with `coverage` for a package."""
    args, pytest_args = _package_parser(unit).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    pkg_dir = REPO_ROOT / args.package
    cmds = _coverage_cmds(
        pkg_dir, 'unit', python, pytest_args or ['-rA'], resolution=args.resolution
    )
    with _resolution_sandbox(pkg_dir, args.resolution):
        for cmd in cmds:
            _run(cmd, cwd=pkg_dir, env=_coverage_env())
    return 0


@_register
def functional(argv: list[str]) -> int:
    """Run functional tests with `coverage` for a package."""
    args, pytest_args = _package_parser(functional).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    cmds = _coverage_cmds(
        REPO_ROOT / args.package,
        'functional',
        python,
        pytest_args or ['-rA'],
        resolution=args.resolution,
    )
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
    pkg_dir = REPO_ROOT / args.package
    with _resolution_sandbox(pkg_dir, args.resolution):
        _run(['bash', '-c', script], cwd=pkg_dir, env=_coverage_env())
    return 0


def _coverage_cmds(
    pkg_dir: pathlib.Path,
    suite: str,
    python: str,
    pytest_args: list[str],
    *,
    resolution: str | None = None,
):
    """Return cmds for `coverage run -m pytest` and `coverage report` for package and suite."""
    data_file_arg = f'--data-file=.report/coverage-{suite}-{python}.db'
    run = [
        *('coverage', 'run', data_file_arg, '--source=src', '-m'),
        *('pytest', '--tb=native', '-vv', f'tests/{suite}', *pytest_args),
    ]
    run_cmd = _uv_cmd(run, pkg_dir=pkg_dir, python=python, groups=[suite], resolution=resolution)
    report = ['coverage', 'report', data_file_arg]
    report_cmd = _uv_cmd(
        report, pkg_dir=pkg_dir, python=python, groups=[suite], resolution=resolution
    )
    return run_cmd, report_cmd


@_register
def combine_coverage(argv: list[str]) -> int:
    """Combine a package's `coverage` reports."""
    args = _package_parser(combine_coverage, resolution=False).parse_args(argv)
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
    pkg_dir = REPO_ROOT / args.package
    with _resolution_sandbox(pkg_dir, args.resolution):
        return _uv_run(
            [
                *('pytest', '--tb=native', '-vv'),
                *('-m', {'k8s': 'not machine_only', 'machine': 'not k8s_only'}[substrate]),
                'tests/integration',
                *(pytest_args or ['-rA']),
            ],
            pkg_dir=pkg_dir,
            python=_resolve_python(args.package, args.python),
            groups=['integration'],
            resolution=args.resolution,
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
        'lib_docs_url',
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


def _package_parser(fn: FunctionType, *, resolution: bool = True) -> argparse.ArgumentParser:
    """Return an `ArgumentParser` with the common `--python`, `--resolution`, `package` args.

    Pass `resolution=False` for a recipe that doesn't resolve dependencies, so that it
    rejects `--resolution` rather than accepting and ignoring it.
    """
    parser = _parser(fn)
    parser.add_argument(
        '--python',
        default=None,
        help="Python version to use, e.g. `3.12` (defaults to the package's minimum).",
    )
    if resolution:
        parser.add_argument(
            '--resolution',
            default=None,
            choices=('highest', 'lowest', 'lowest-direct'),
            help=(
                'Dependency resolution strategy to pass to `uv run --resolution=...`. '
                "When set, the package's uv.lock is bypassed (no `--locked`). "
                'Useful for testing against the lowest declared or highest available dependency '
                'versions, since a charm resolves deps at pack time from its own lockfile.'
            ),
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


@contextlib.contextmanager
def _resolution_sandbox(pkg_dir: pathlib.Path, resolution: str | None) -> Iterator[None]:
    """Keep a `--resolution` run from changing the package's `uv.lock` or `.venv`.

    `uv run --resolution=<mode>` re-resolves dependencies, writes the result back to the
    package's `uv.lock`, and syncs the project environment to match. That's fine in CI (each
    job is a fresh checkout) but disruptive locally: the lockfile shows up as modified, and the
    `.venv` an editor is probably using is left on the alternative versions. When `resolution`
    is set, this points `UV_PROJECT_ENVIRONMENT` at a temporary directory for the duration, and
    restores the lock file bytes afterwards.
    """
    if resolution is None:
        yield
        return
    lock = pkg_dir / 'uv.lock'
    saved = lock.read_bytes() if lock.exists() else None
    previous_env = os.environ.get('UV_PROJECT_ENVIRONMENT')
    try:
        with tempfile.TemporaryDirectory(prefix='charmlibs-resolution-') as tmp:
            os.environ['UV_PROJECT_ENVIRONMENT'] = str(pathlib.Path(tmp) / 'venv')
            yield
    finally:
        if previous_env is None:
            os.environ.pop('UV_PROJECT_ENVIRONMENT', None)
        else:
            os.environ['UV_PROJECT_ENVIRONMENT'] = previous_env
        if saved is not None and lock.read_bytes() != saved:
            lock.write_bytes(saved)


def _uv_run(
    args: Sequence[str | pathlib.Path],
    *,
    pkg_dir: pathlib.Path,
    python: str,
    groups: Sequence[str] = (),
    resolution: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    """Run `uv run ... <args>` in `pkg_dir`, returning the exit code."""
    cmd = _uv_cmd(args, pkg_dir=pkg_dir, python=python, groups=groups, resolution=resolution)
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
    resolution: str | None = None,
) -> list[str | pathlib.Path]:
    """Build a `uv run ... <args>` command list to be executed in `pkg_dir`.

    If `resolution` is set, `--resolution=<mode>` is passed and `--locked` is omitted so
    uv re-resolves against the mode instead of pinning to the checked-in lockfile.
    """
    cmd = ['uv', 'run', '--with-requirements', TEST_REQUIREMENTS, '--python', python]
    if resolution is not None:
        cmd.append(f'--resolution={resolution}')
    elif (pkg_dir / 'uv.lock').exists():
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
