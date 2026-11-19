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

# ruff: noqa: D103 (function docstrings)

"""Unit tests for the just script."""

import os
import pathlib
from collections.abc import Callable, Sequence
from unittest.mock import patch

import just
import pytest


class TestUVCmd:
    test_reqs = pathlib.Path(__file__).parent.parent.parent / 'test-requirements.txt'

    @pytest.mark.parametrize(
        ('groups', 'args'),
        [
            (['one'], ['--group', 'one']),
            (['one', 'two'], ['--group', 'one', '--group', 'two']),
            ([], []),
            (['missing'], []),
            (['one', 'two', 'missing'], ['--group', 'one', '--group', 'two']),
        ],
    )
    def test_ok(self, tmp_path: pathlib.Path, groups: list[str], args: list[str]):
        (tmp_path / 'pyproject.toml').write_text('[dependency-groups]\none = []\ntwo = []')
        assert just._uv_cmd([], pkg_dir=tmp_path, python='fakepy', groups=groups) == [
            'uv',
            'run',
            '--with-requirements',
            self.test_reqs,
            '--python',
            'fakepy',
            *args,
        ]

    def test_with_uv_lock(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').touch()
        (tmp_path / 'uv.lock').touch()
        result = just._uv_cmd(['pytest'], pkg_dir=tmp_path, python='3.12', groups=[])
        assert '--locked' in result
        assert result == [
            'uv',
            'run',
            '--with-requirements',
            self.test_reqs,
            '--python',
            '3.12',
            '--locked',
            'pytest',
        ]

    def test_with_python(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').touch()
        result = just._uv_cmd(['pytest'], pkg_dir=tmp_path, python='foo', groups=[])
        assert '--python' in result
        assert result == [
            'uv',
            'run',
            '--with-requirements',
            self.test_reqs,
            '--python',
            'foo',
            'pytest',
        ]

    def test_with_resolution_omits_locked(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').touch()
        (tmp_path / 'uv.lock').touch()
        result = just._uv_cmd(
            ['pytest'], pkg_dir=tmp_path, python='3.12', groups=[], resolution='lowest-direct'
        )
        assert '--locked' not in result
        assert result == [
            'uv',
            'run',
            '--with-requirements',
            self.test_reqs,
            '--python',
            '3.12',
            '--resolution=lowest-direct',
            'pytest',
        ]

    @pytest.mark.parametrize('resolution', ['highest', 'lowest', 'lowest-direct'])
    def test_with_resolution_no_lock(self, tmp_path: pathlib.Path, resolution: str):
        (tmp_path / 'pyproject.toml').touch()
        result = just._uv_cmd(
            ['pytest'], pkg_dir=tmp_path, python='3.12', groups=[], resolution=resolution
        )
        assert f'--resolution={resolution}' in result
        assert '--locked' not in result

    def test_no_sync(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').touch()
        (tmp_path / 'uv.lock').touch()
        result = just._uv_cmd(['pytest'], pkg_dir=tmp_path, python='3.12', no_sync=True)
        assert '--no-sync' in result
        assert '--locked' not in result
        assert not any(str(part).startswith('--resolution') for part in result)

    def test_no_sync_and_resolution_are_exclusive(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').touch()
        with pytest.raises(ValueError):
            just._uv_cmd(
                [], pkg_dir=tmp_path, python='3.12', resolution='lowest-direct', no_sync=True
            )


class TestResolutionSandbox:
    def test_restores_modified_lock(self, tmp_path: pathlib.Path):
        lock = tmp_path / 'uv.lock'
        lock.write_bytes(b'original')
        with just._resolution_sandbox(tmp_path, 'lowest-direct'):
            lock.write_bytes(b'mutated')
        assert lock.read_bytes() == b'original'

    def test_leaves_unmodified_lock_untouched(self, tmp_path: pathlib.Path):
        lock = tmp_path / 'uv.lock'
        lock.write_bytes(b'original')
        with just._resolution_sandbox(tmp_path, 'lowest-direct'):
            pass
        assert lock.read_bytes() == b'original'

    def test_no_resolution_does_nothing(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv('UV_PROJECT_ENVIRONMENT', raising=False)
        lock = tmp_path / 'uv.lock'
        lock.write_bytes(b'original')
        with just._resolution_sandbox(tmp_path, None):
            assert 'UV_PROJECT_ENVIRONMENT' not in os.environ
            lock.write_bytes(b'mutated')
        assert lock.read_bytes() == b'mutated'

    def test_no_lock_file_is_not_created(self, tmp_path: pathlib.Path):
        with just._resolution_sandbox(tmp_path, 'lowest-direct'):
            pass
        assert not (tmp_path / 'uv.lock').exists()

    def test_removes_a_lock_file_it_created(self, tmp_path: pathlib.Path):
        with just._resolution_sandbox(tmp_path, 'lowest-direct'):
            (tmp_path / 'uv.lock').write_bytes(b'created')
        assert not (tmp_path / 'uv.lock').exists()

    def test_restores_on_exception(self, tmp_path: pathlib.Path):
        lock = tmp_path / 'uv.lock'
        lock.write_bytes(b'original')
        with pytest.raises(RuntimeError, match='boom'):
            with just._resolution_sandbox(tmp_path, 'lowest-direct'):
                lock.write_bytes(b'mutated')
                raise RuntimeError('boom')
        assert lock.read_bytes() == b'original'

    def test_uses_a_temporary_project_environment(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv('UV_PROJECT_ENVIRONMENT', raising=False)
        with just._resolution_sandbox(tmp_path, 'lowest-direct'):
            venv = pathlib.Path(os.environ['UV_PROJECT_ENVIRONMENT'])
            assert not venv.is_relative_to(tmp_path)
            assert venv.parent.is_dir()
        assert 'UV_PROJECT_ENVIRONMENT' not in os.environ
        assert not venv.parent.exists()

    def test_restores_existing_project_environment(self, tmp_path: pathlib.Path):
        with patch.dict('os.environ', {'UV_PROJECT_ENVIRONMENT': 'mine'}):
            with just._resolution_sandbox(tmp_path, 'lowest-direct'):
                assert os.environ['UV_PROJECT_ENVIRONMENT'] != 'mine'
            assert os.environ['UV_PROJECT_ENVIRONMENT'] == 'mine'

    @pytest.mark.parametrize(
        'recipe',
        [just.check, just.lint, just.static, just.unit, just.functional, just.integration_k8s],
    )
    def test_recipes_use_the_sandbox(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        recipe: Callable[[list[str]], int],
    ):
        monkeypatch.delenv('UV_PROJECT_ENVIRONMENT', raising=False)
        (tmp_path / 'pyproject.toml').touch()
        lock = tmp_path / 'uv.lock'
        lock.write_bytes(b'original')
        project_envs: list[str | None] = []

        def fake_run(cmd: Sequence[str], *, env: dict[str, str] | None = None, **_: object):
            if any('--resolution=' in str(part) for part in cmd):
                lock.write_bytes(b'mutated')
                project_envs.append(
                    (os.environ if env is None else env).get('UV_PROJECT_ENVIRONMENT')
                )
            return 0

        monkeypatch.setattr(just, '_run', fake_run)
        recipe(['--python', '3.12', '--resolution', 'lowest-direct', str(tmp_path)])
        assert project_envs
        assert all(project_envs)
        assert lock.read_bytes() == b'original'


class TestUnitLowestDirectFile:
    def _run_unit(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, resolution: str
    ) -> list[list[str]]:
        monkeypatch.delenv('UV_PROJECT_ENVIRONMENT', raising=False)
        (tmp_path / 'pyproject.toml').write_text('[dependency-groups]\nunit = []')
        (tmp_path / just.LOWEST_DIRECT_FILE).write_text('-e .\n')
        cmds: list[list[str]] = []

        def fake_run(cmd: Sequence[str | pathlib.Path], **_: object):
            cmds.append([str(part) for part in cmd])
            return 0

        monkeypatch.setattr(just, '_run', fake_run)
        just.unit(['--python', '3.12', '--resolution', resolution, str(tmp_path)])
        return cmds

    def test_lowest_direct_installs_the_file(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        cmds = self._run_unit(tmp_path, monkeypatch, 'lowest-direct')
        assert cmds[0][:3] == ['uv', 'venv', '--quiet']
        assert cmds[1][:3] == ['uv', 'pip', 'sync']
        assert cmds[1][-1] == just.LOWEST_DIRECT_FILE
        for cmd in cmds[2:]:
            assert '--no-sync' in cmd
            assert not any(part.startswith('--resolution') for part in cmd)

    def test_highest_ignores_the_file(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        cmds = self._run_unit(tmp_path, monkeypatch, 'highest')
        assert all(cmd[:2] == ['uv', 'run'] for cmd in cmds)
        assert all('--resolution=highest' in cmd for cmd in cmds)


class TestIsExample:
    @pytest.mark.parametrize(
        ('package', 'expected'),
        [
            ('.example', True),
            ('.tutorial', True),
            ('interfaces/.example', True),
            ('interfaces/.example/testing', True),
            ('pathops', False),
            ('interfaces/tls-certificates', False),
            ('interfaces/tls-certificates/testing', False),
        ],
    )
    def test_ok(self, package: str, expected: bool):
        assert just._is_example(package) is expected


class TestReadExcludeNewer:
    def test_ok(self, tmp_path: pathlib.Path):
        path = tmp_path / just.LOWEST_DIRECT_FILE
        path.write_text('# Generated\n# exclude-newer: 2026-01-02T03:04:05Z\nops==2.0\n')
        assert just._read_exclude_newer(path) == '2026-01-02T03:04:05Z'

    def test_missing_line(self, tmp_path: pathlib.Path):
        path = tmp_path / just.LOWEST_DIRECT_FILE
        path.write_text('ops==2.0\n')
        assert just._read_exclude_newer(path) is None

    def test_missing_file(self, tmp_path: pathlib.Path):
        assert just._read_exclude_newer(tmp_path / just.LOWEST_DIRECT_FILE) is None


class TestLowestDirect:
    old = '2026-01-01T00:00:00Z'
    now = '2026-06-01T00:00:00Z'

    @pytest.fixture
    def pkg(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
        monkeypatch.setattr(just, 'REPO_ROOT', tmp_path)
        monkeypatch.setattr(just, '_now', lambda: self.now)
        pkg_dir = tmp_path / 'pkg'
        (pkg_dir / 'tests' / 'unit').mkdir(parents=True)
        return pkg_dir

    def _fake_export(
        self, monkeypatch: pytest.MonkeyPatch, resolvable: Callable[[str], bool] = lambda _: True
    ) -> list[str]:
        calls: list[str] = []

        def fake(package: str, exclude_newer: str, *, quiet: bool = False) -> str | None:
            calls.append(exclude_newer)
            return f'# exclude-newer: {exclude_newer}\n' if resolvable(exclude_newer) else None

        monkeypatch.setattr(just, '_export_lowest_direct', fake)
        return calls

    def test_writes_a_new_file(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        self._fake_export(monkeypatch)
        assert just.lowest_direct(['pkg']) == 0
        assert just._read_exclude_newer(pkg / just.LOWEST_DIRECT_FILE) == self.now

    def test_keeps_the_existing_time(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        (pkg / just.LOWEST_DIRECT_FILE).write_text(f'# exclude-newer: {self.old}\n')
        calls = self._fake_export(monkeypatch)
        assert just.lowest_direct(['pkg']) == 0
        assert calls == [self.old]
        assert just._read_exclude_newer(pkg / just.LOWEST_DIRECT_FILE) == self.old

    def test_moves_on_if_the_existing_time_fails(
        self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        (pkg / just.LOWEST_DIRECT_FILE).write_text(f'# exclude-newer: {self.old}\n')
        calls = self._fake_export(monkeypatch, resolvable=lambda t: t == self.now)
        assert just.lowest_direct(['pkg']) == 0
        assert calls == [self.old, self.now]
        assert just._read_exclude_newer(pkg / just.LOWEST_DIRECT_FILE) == self.now

    def test_upgrade(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        (pkg / just.LOWEST_DIRECT_FILE).write_text(f'# exclude-newer: {self.old}\n')
        calls = self._fake_export(monkeypatch)
        assert just.lowest_direct(['--upgrade', 'pkg']) == 0
        assert calls == [self.now]

    def test_write_fails_if_unresolvable(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        self._fake_export(monkeypatch, resolvable=lambda _: False)
        assert just.lowest_direct(['pkg']) == 1
        assert not (pkg / just.LOWEST_DIRECT_FILE).exists()

    def test_check_up_to_date(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        (pkg / just.LOWEST_DIRECT_FILE).write_text(f'# exclude-newer: {self.old}\n')
        calls = self._fake_export(monkeypatch)
        assert just.lowest_direct(['--check', 'pkg']) == 0
        assert calls == [self.old]

    def test_check_stale(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        (pkg / just.LOWEST_DIRECT_FILE).write_text(f'# exclude-newer: {self.old}\nops==1\n')
        self._fake_export(monkeypatch)
        assert just.lowest_direct(['--check', 'pkg']) == 1
        assert 'ops==1' in (pkg / just.LOWEST_DIRECT_FILE).read_text()  # not rewritten

    def test_check_missing(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        self._fake_export(monkeypatch)
        assert just.lowest_direct(['--check', 'pkg']) == 1
        assert not (pkg / just.LOWEST_DIRECT_FILE).exists()

    def test_check_missing_and_unresolvable(
        self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._fake_export(monkeypatch, resolvable=lambda _: False)
        assert just.lowest_direct(['--check', 'pkg']) == 0

    def test_check_no_time(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        (pkg / just.LOWEST_DIRECT_FILE).write_text('ops==1\n')
        self._fake_export(monkeypatch)
        assert just.lowest_direct(['--check', 'pkg']) == 1

    @pytest.mark.parametrize('package', ['.example', 'no-unit-tests'])
    def test_skips(self, pkg: pathlib.Path, monkeypatch: pytest.MonkeyPatch, package: str):
        (pkg.parent / package).mkdir()
        calls = self._fake_export(monkeypatch)
        assert just.lowest_direct(['--check', package]) == 0
        assert just.lowest_direct([package]) == 0
        assert calls == []

    def test_check_and_upgrade_are_exclusive(self, pkg: pathlib.Path):
        with pytest.raises(SystemExit):
            just.lowest_direct(['--check', '--upgrade', 'pkg'])


class TestDependencyGroups:
    def test_ok(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').write_text("""
[dependency-groups]
foo = []
bar = ["pytest"]
baz = []
""")
        assert just._dependency_groups(tmp_path) == {'foo', 'bar', 'baz'}

    def test_no_groups_table(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').touch()
        assert just._dependency_groups(tmp_path) == set()

    def test_empty_groups_table(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').write_text('[dependency-groups]\n')
        assert just._dependency_groups(tmp_path) == set()


class TestRequiresPythonMinimum:
    @pytest.mark.parametrize(
        ('requires', 'expected'),
        [
            ('>=3.11', '3.11'),
            ('~=3.10.2', '3.10'),
            ('>=3.10,<4.0', '3.10'),
            ('>=3.9,!=3.9.*,<4.0', '3.9'),  # No resolution, just regex.
        ],
    )
    def test_ok(self, tmp_path: pathlib.Path, requires: str, expected: str):
        (tmp_path / 'pyproject.toml').write_text(f'[project]\nrequires-python = "{requires}"')
        assert just._requires_python_minimum(tmp_path) == expected

    def test_no_minimum(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').write_text('[project]\nrequires-python = "<3.12"')
        with pytest.raises(ValueError, match='minimum'):
            just._requires_python_minimum(tmp_path)


class TestResolvePython:
    def test_explicit_immediately_returns(self):
        assert just._resolve_python('', 'foo') == 'foo'

    @pytest.mark.parametrize(
        ('minimum', 'default', 'expected'),
        [
            ('1.0', '0.0', '1.0'),
            ('0.42', '2.0', '2.0'),
            ('3.10', '3.10', '3.10'),
        ],
    )
    def test_resolve_python_from_minimum(self, minimum: str, default: str, expected: str):
        with (
            patch('just._requires_python_minimum', return_value=minimum),
            patch('just.DEFAULT_PYTHON', default),
        ):
            assert just._resolve_python('', None) == expected


class TestCoverageCmds:
    def test_ok(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(just, '_uv_cmd', lambda cmd, *_, **__: cmd)  # type: ignore
        (tmp_path / 'pyproject.toml').touch()
        run_cmd, report_cmd = just._coverage_cmds(
            tmp_path, 'fakesuite', 'fakepy', ['--fake-opt', 'fake-val']
        )
        assert run_cmd[:2] == ['coverage', 'run']
        assert '--data-file=.report/coverage-fakesuite-fakepy.db' in run_cmd
        assert 'tests/fakesuite' in run_cmd
        assert '--fake-opt' in run_cmd
        assert 'fake-val' in run_cmd
        assert report_cmd[:2] == ['coverage', 'report']
        assert '--data-file=.report/coverage-fakesuite-fakepy.db' in report_cmd


class TestColors:
    @pytest.mark.parametrize('no_color', ['1', 'anything'])
    def test_no_color_alone_disables(self, monkeypatch: pytest.MonkeyPatch, no_color: str):
        monkeypatch.delenv('FORCE_COLOR', raising=False)
        monkeypatch.setenv('NO_COLOR', no_color)
        assert just.Colors._enabled() is False

    @pytest.mark.parametrize('no_color', ['', '0'])
    def test_falsy_no_color_does_not_disable(self, monkeypatch: pytest.MonkeyPatch, no_color: str):
        monkeypatch.delenv('FORCE_COLOR', raising=False)
        monkeypatch.setenv('NO_COLOR', no_color)
        with patch('sys.stdout.isatty', return_value=True):
            assert just.Colors._enabled() is True

    @pytest.mark.parametrize('force_color', ['1', 'anything'])
    def test_force_color_alone_enables(self, monkeypatch: pytest.MonkeyPatch, force_color: str):
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.setenv('FORCE_COLOR', force_color)
        with patch('sys.stdout.isatty', return_value=False):
            assert just.Colors._enabled() is True

    @pytest.mark.parametrize('force_color', ['', '0'])
    def test_falsy_force_color_does_not_enable(
        self, monkeypatch: pytest.MonkeyPatch, force_color: str
    ):
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.setenv('FORCE_COLOR', force_color)
        with patch('sys.stdout.isatty', return_value=False):
            assert just.Colors._enabled() is False

    @pytest.mark.parametrize('force_color', ['1', ''])
    @pytest.mark.parametrize('no_color', ['1', ''])
    def test_force_color_overrides_no_color(
        self, monkeypatch: pytest.MonkeyPatch, force_color: str, no_color: str
    ):
        monkeypatch.setenv('NO_COLOR', no_color)
        monkeypatch.setenv('FORCE_COLOR', force_color)
        with patch('sys.stdout.isatty', return_value=False):
            assert just.Colors._enabled() is bool(force_color)

    @pytest.mark.parametrize('isatty', [True, False])
    def test_isatty(self, monkeypatch: pytest.MonkeyPatch, isatty: bool):
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.delenv('FORCE_COLOR', raising=False)
        with patch('sys.stdout.isatty', return_value=isatty):
            assert just.Colors._enabled() is isatty

    def test_enabled(self):
        with patch('just.Colors._enabled', return_value=True):
            colors = just.Colors()
            message = just._quick_start()
        assert all((colors.bold, colors.normal, colors.cyan))
        assert 'just help' in message  # Correct message.
        assert '\033[' in message  # With colors.

    def test_disabled(self):
        with patch('just.Colors._enabled', return_value=False):
            colors = just.Colors()
            message = just._quick_start()
        assert not any((colors.bold, colors.normal, colors.cyan))
        assert 'just help' in message  # Correct message.
        assert '\033[' not in message  # No colors.


class TestMain:
    def test_ok(self):
        result = just.main(['help'])
        assert result == 0

    def test_no_args(self):
        result = just.main([])
        assert result == 0

    def test_unknown_recipe(self):
        result = just.main(['unknown-command'])
        assert result > 0


class TestParser:
    def test_ok(self):
        parser = just._parser(just.help)
        assert parser.prog == 'just help'


class TestPackageParser:
    def test_ok(self):
        """_package_parser adds --python and package positional arg."""
        parser = just._package_parser(just.unit)
        args = parser.parse_args(['--python', 'py', 'foo'])
        assert args.python == 'py'
        assert args.package == 'foo'

    def test_defaults(self):
        """_package_parser defaults --python to None and package to first arg."""
        parser = just._package_parser(just.unit)
        args = parser.parse_args(['foo'])
        assert args.python is None
        assert args.package == 'foo'
        assert args.resolution is None

    @pytest.mark.parametrize('resolution', ['highest', 'lowest', 'lowest-direct'])
    def test_resolution_choice(self, resolution: str):
        parser = just._package_parser(just.unit)
        args = parser.parse_args(['--resolution', resolution, 'foo'])
        assert args.resolution == resolution

    def test_resolution_rejects_unknown(self, capsys: pytest.CaptureFixture[str]):
        parser = just._package_parser(just.unit)
        with pytest.raises(SystemExit):
            parser.parse_args(['--resolution', 'bogus', 'foo'])
        assert 'invalid choice' in capsys.readouterr().err

    def test_without_resolution(self, capsys: pytest.CaptureFixture[str]):
        parser = just._package_parser(just.combine_coverage, resolution=False)
        assert parser.parse_args(['foo']).package == 'foo'
        with pytest.raises(SystemExit):
            parser.parse_args(['--resolution', 'lowest-direct', 'foo'])
        assert 'unrecognized arguments' in capsys.readouterr().err


class TestRun:
    def test_ok(self):
        with patch('subprocess.call', return_value=0):
            assert just._run([], check=True) == 0

    def test_check_exits_on_failure(self):
        with patch('subprocess.call', return_value=1), pytest.raises(SystemExit):
            just._run([], check=True)

    def test_check_false_returns_code(self):
        with patch('subprocess.call', return_value=42):
            assert just._run([], check=False) == 42

    def test_removes_virtual_env(self):
        with patch('subprocess.call', return_value=0) as mock_call:
            just._run([], env={'VIRTUAL_ENV': 'fake-env'})
            call_kwargs = mock_call.call_args.kwargs
            assert 'VIRTUAL_ENV' not in call_kwargs['env']


class TestUVRun:
    def test_ok(self, tmp_path: pathlib.Path):
        (tmp_path / 'pyproject.toml').touch()
        with patch('just._run', return_value=0) as mock_run:
            assert just._uv_run(['fake-cmd'], pkg_dir=tmp_path, python='3.12') == 0
            uv_run_cmd = mock_run.call_args.args[0]
            assert uv_run_cmd[:2] == ['uv', 'run']
            assert 'fake-cmd' in uv_run_cmd


class TestCoverageEnv:
    def test_ok(self):
        env = just._coverage_env()
        assert 'COVERAGE_RCFILE' in env
        assert env['COVERAGE_RCFILE'].endswith('pyproject.toml')

    def test_preserves_existing(self):
        with patch.dict('os.environ', {'EXISTING': 'value'}, clear=False):
            env = just._coverage_env()
            assert env['EXISTING'] == 'value'
