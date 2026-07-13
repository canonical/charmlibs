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

# ruff: noqa: D101, D102, D103 (test docstrings)

"""Unit tests for the check_codeowners script."""

import importlib
import pathlib

check_codeowners = importlib.import_module('check_codeowners')
Entry = check_codeowners.Entry
PurePath = pathlib.PurePosixPath


def _files(*paths: str) -> list[pathlib.PurePosixPath]:
    return [PurePath(p) for p in paths]


def _entries(*patterns: str) -> dict[pathlib.PurePosixPath, Entry]:
    """Build an entries dict (keyed by repo-relative target) from `pattern` strings."""
    return {
        PurePath(p.strip('/')): Entry(pattern=p, owners=('@canonical/team',)) for p in patterns
    }


class TestParseCodeowners:
    def test_keys_by_repo_relative_target(self):
        text = '/apt/ @canonical/team  # trailing comment\n'
        assert check_codeowners.parse_codeowners(text) == {
            PurePath('apt'): Entry(pattern='/apt/', owners=('@canonical/team',))
        }

    def test_ignores_comments_and_blanks(self):
        text = '# a comment\n\n/apt/ @canonical/team\n'
        assert list(check_codeowners.parse_codeowners(text)) == [PurePath('apt')]

    def test_multiple_owners(self):
        text = '/foo/ @canonical/one @canonical/two\n'
        assert check_codeowners.parse_codeowners(text)[PurePath('foo')] == Entry(
            pattern='/foo/', owners=('@canonical/one', '@canonical/two')
        )

    def test_entry_without_owner(self):
        text = '/interfaces/index.json\n'
        assert check_codeowners.parse_codeowners(text)[PurePath('interfaces/index.json')] == Entry(
            pattern='/interfaces/index.json', owners=()
        )

    def test_drops_wildcard_patterns(self):
        text = '* @canonical/team\n/*.md @canonical/team\n/foo/[abc] @t\n/apt/ @canonical/team\n'
        # Only the anchored, wildcard-free entry survives.
        assert list(check_codeowners.parse_codeowners(text)) == [PurePath('apt')]

    def test_empty(self):
        assert check_codeowners.parse_codeowners('') == {}


class TestChildrenOf:
    def test_root_children(self):
        files = _files('README.md', 'apt/pyproject.toml', 'apt/src/__init__.py')
        assert check_codeowners.children_of(check_codeowners.ROOT, files) == _files(
            'README.md', 'apt'
        )

    def test_directory_children(self):
        files = _files('apt/pyproject.toml', 'apt/src/__init__.py')
        assert check_codeowners.children_of(PurePath('apt'), files) == _files(
            'apt/pyproject.toml', 'apt/src'
        )

    def test_no_children_for_unrelated_dir(self):
        files = _files('apt/x.py')
        assert check_codeowners.children_of(PurePath('snap'), files) == []


class TestRender:
    def test_directory_gets_trailing_slash(self):
        files = _files('apt/x.py')
        assert check_codeowners.render(PurePath('apt'), files) == '/apt/'

    def test_file_has_no_trailing_slash(self):
        files = _files('README.md')
        assert check_codeowners.render(PurePath('README.md'), files) == '/README.md'


class TestFindBadEntries:
    def test_existing_paths_are_not_bad(self, tmp_path: pathlib.Path):
        (tmp_path / 'apt').mkdir()
        (tmp_path / 'interfaces' / 'foo').mkdir(parents=True)
        (tmp_path / 'interfaces' / 'foo' / 'ruff.toml').touch()
        entries = _entries('/apt/', '/interfaces/foo/', '/interfaces/foo/ruff.toml')
        assert check_codeowners.find_bad_entries(entries, tmp_path) == []

    def test_missing_path_is_bad(self, tmp_path: pathlib.Path):
        (tmp_path / 'apt').mkdir()
        entries = _entries('/apt/', '/gone/')
        bad = check_codeowners.find_bad_entries(entries, tmp_path)
        assert [e.pattern for e in bad] == ['/gone/']

    def test_directory_entry_without_trailing_slash_is_bad(self, tmp_path: pathlib.Path):
        (tmp_path / 'apt').mkdir()
        entries = _entries('/apt')  # missing the trailing slash
        bad = check_codeowners.find_bad_entries(entries, tmp_path)
        assert [e.pattern for e in bad] == ['/apt']

    def test_file_entry_with_trailing_slash_is_bad(self, tmp_path: pathlib.Path):
        (tmp_path / 'README.md').touch()
        entries = _entries('/README.md/')  # stray trailing slash on a file
        bad = check_codeowners.find_bad_entries(entries, tmp_path)
        assert [e.pattern for e in bad] == ['/README.md/']


class TestFindUnownedDirs:
    def test_path_with_own_entry_passes(self):
        entries = _entries('/apt/')
        files = _files('apt/src/x.py')
        assert check_codeowners.find_unowned_dirs(entries, files) == []

    def test_trailing_slash_is_ignored_when_matching(self):
        # Matching is slash-insensitive (PurePosixPath); find_bad_entries enforces the slash.
        entries = _entries('/apt')  # no trailing slash, but still matches the apt directory
        files = _files('apt/src/x.py')
        assert check_codeowners.find_unowned_dirs(entries, files) == []

    def test_all_children_owned_passes(self):
        # Split interface entries: interfaces/foo has no entry, but each of its children does.
        entries = _entries(
            '/interfaces/', '/interfaces/foo/interface/', '/interfaces/foo/ruff.toml'
        )
        files = _files('interfaces/foo/interface/v0/schema.py', 'interfaces/foo/ruff.toml')
        assert check_codeowners.find_unowned_dirs(entries, files) == []

    def test_all_children_disowned_passes(self):
        # Children with ownerless entries are explicitly disowned, which satisfies the parent.
        entries = {
            PurePath('interfaces'): Entry('/interfaces/', ('@canonical/team',)),
            PurePath('interfaces/foo/interface'): Entry('/interfaces/foo/interface/', ()),
            PurePath('interfaces/foo/ruff.toml'): Entry('/interfaces/foo/ruff.toml', ()),
        }
        files = _files('interfaces/foo/interface/v0/schema.py', 'interfaces/foo/ruff.toml')
        assert check_codeowners.find_unowned_dirs(entries, files) == []

    def test_some_children_unowned_is_unowned(self):
        # /interfaces/ is owned; only interfaces/foo (whose ruff.toml lacks an entry) is unowned.
        entries = _entries('/interfaces/', '/interfaces/foo/interface/')
        files = _files('interfaces/foo/interface/v0/schema.py', 'interfaces/foo/ruff.toml')
        assert check_codeowners.find_unowned_dirs(entries, files) == [PurePath('interfaces/foo')]

    def test_rule_is_not_recursive(self):
        # A grandchild entry must NOT satisfy a child; `interfaces/foo/interface` has no entry,
        # only its own child does, so `interfaces/foo` is not owned.
        entries = _entries('/interfaces/', '/interfaces/foo/interface/v0/')
        files = _files('interfaces/foo/interface/v0/schema.py')
        assert check_codeowners.find_unowned_dirs(entries, files) == [PurePath('interfaces/foo')]

    def test_no_entries_means_unowned(self):
        # The catch-all `*` is dropped by the parser, so find_unowned_dirs never sees it.
        files = _files('apt/src/x.py')
        assert check_codeowners.find_unowned_dirs({}, files) == [PurePath('apt')]

    def test_parent_dir_entry_does_not_own_child(self):
        # `/interfaces/` (the fallback) must not be treated as owning a specific interface.
        entries = _entries('/interfaces/')
        files = _files('interfaces/foo/ruff.toml')
        assert check_codeowners.find_unowned_dirs(entries, files) == [PurePath('interfaces/foo')]

    def test_top_level_file_needs_own_entry(self):
        entries = _entries('/other')
        files = _files('README.md')
        assert check_codeowners.find_unowned_dirs(entries, files) == [PurePath('README.md')]
