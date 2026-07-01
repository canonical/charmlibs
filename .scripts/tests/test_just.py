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

import pathlib
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


class TestColorsEnabled:
    def test_no_color_disables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('NO_COLOR', '1')
        monkeypatch.setenv('FORCE_COLOR', '1')  # NO_COLOR takes precedence.
        assert just.Colors._enabled() is False

    def test_empty_no_color_does_not_disable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('NO_COLOR', '')  # Empty NO_COLOR is ignored per no-color.org.
        monkeypatch.delenv('FORCE_COLOR', raising=False)
        with patch('sys.stdout.isatty', return_value=True):
            assert just.Colors._enabled() is True

    def test_force_color_enables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.setenv('FORCE_COLOR', '1')
        with patch('sys.stdout.isatty', return_value=False):
            assert just.Colors._enabled() is True

    def test_empty_force_color_enables(self, monkeypatch: pytest.MonkeyPatch):
        # Empty FORCE_COLOR still forces color on, per force-color.org.
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.setenv('FORCE_COLOR', '')
        with patch('sys.stdout.isatty', return_value=False):
            assert just.Colors._enabled() is True

    def test_tty_enables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.delenv('FORCE_COLOR', raising=False)
        with patch('sys.stdout.isatty', return_value=True):
            assert just.Colors._enabled() is True

    def test_non_tty_disables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv('NO_COLOR', raising=False)
        monkeypatch.delenv('FORCE_COLOR', raising=False)
        with patch('sys.stdout.isatty', return_value=False):
            assert just.Colors._enabled() is False


class TestColors:
    def test_enabled(self):
        with patch('just.Colors._enabled', return_value=True):
            colors = just.Colors()
        assert (colors.bold, colors.normal, colors.cyan) == ('\033[1m', '\033[0m', '\033[36m')

    def test_disabled(self):
        with patch('just.Colors._enabled', return_value=False):
            colors = just.Colors()
        assert (colors.bold, colors.normal, colors.cyan) == ('', '', '')


class TestQuickStart:
    def test_with_colors(self):
        with patch('just.Colors._enabled', return_value=True):
            message = just._quick_start()
        assert '\033[' in message
        assert 'just help' in message

    def test_without_colors(self):
        with patch('just.Colors._enabled', return_value=False):
            message = just._quick_start()
        assert '\033[' not in message
        assert 'just help' in message


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
