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

import pytest

check_codeowners = importlib.import_module('check_codeowners')
Entry = check_codeowners.Entry


class TestParseCodeowners:
    def test_ignores_comments_and_blanks(self):
        text = '# a comment\n\n/apt/ @canonical/team  # trailing comment\n'
        assert check_codeowners.parse_codeowners(text) == [
            Entry(pattern='/apt/', owners=('@canonical/team',))
        ]

    def test_multiple_owners(self):
        text = '/foo/ @canonical/one @canonical/two\n'
        assert check_codeowners.parse_codeowners(text) == [
            Entry(pattern='/foo/', owners=('@canonical/one', '@canonical/two'))
        ]

    def test_entry_without_owner(self):
        text = '/interfaces/index.json\n'
        assert check_codeowners.parse_codeowners(text) == [
            Entry(pattern='/interfaces/index.json', owners=())
        ]

    def test_empty(self):
        assert check_codeowners.parse_codeowners('') == []


class TestEntryTarget:
    @pytest.mark.parametrize(
        ('pattern', 'expected'),
        [
            ('/apt/', 'apt'),
            ('/apt', 'apt'),
            ('/interfaces/foo/interface/', 'interfaces/foo/interface'),
            ('/interfaces/foo/ruff.toml', 'interfaces/foo/ruff.toml'),
        ],
    )
    def test_path_patterns(self, pattern: str, expected: str):
        assert check_codeowners.entry_target(pattern) == pathlib.PurePosixPath(expected)

    @pytest.mark.parametrize('pattern', ['*', '/*.md', '/foo/*', '/foo/?ar', '/foo/[abc]'])
    def test_glob_patterns_are_not_targets(self, pattern: str):
        assert check_codeowners.entry_target(pattern) is None


class TestFindOrphanEntries:
    def test_existing_paths_are_not_orphans(self, tmp_path: pathlib.Path):
        (tmp_path / 'apt').mkdir()
        (tmp_path / 'interfaces' / 'foo').mkdir(parents=True)
        (tmp_path / 'interfaces' / 'foo' / 'ruff.toml').touch()
        entries = [
            Entry('/apt/', ('@canonical/team',)),
            Entry('/interfaces/foo/', ('@canonical/team',)),
            Entry('/interfaces/foo/ruff.toml', ('@canonical/team',)),
        ]
        assert check_codeowners.find_orphan_entries(entries, tmp_path) == []

    def test_missing_path_is_orphan(self, tmp_path: pathlib.Path):
        (tmp_path / 'apt').mkdir()
        entries = [
            Entry('/apt/', ('@canonical/team',)),
            Entry('/gone/', ('@canonical/team',)),
        ]
        assert check_codeowners.find_orphan_entries(entries, tmp_path) == ['/gone/']

    def test_glob_entries_are_ignored(self, tmp_path: pathlib.Path):
        entries = [Entry('*', ('@canonical/team',)), Entry('/*.md', ('@canonical/team',))]
        assert check_codeowners.find_orphan_entries(entries, tmp_path) == []


class TestFindUnownedDirs:
    def test_whole_dir_entry_is_owned(self):
        entries = [Entry('/apt/', ('@canonical/team',))]
        assert check_codeowners.find_unowned_dirs(['apt'], entries) == []

    def test_entry_inside_dir_counts_as_owned(self):
        # Split interface entries: the dir itself has no direct entry, but content does.
        entries = [
            Entry('/interfaces/foo/interface/', ('@canonical/team',)),
            Entry('/interfaces/foo/ruff.toml', ('@canonical/team',)),
        ]
        assert check_codeowners.find_unowned_dirs(['interfaces/foo'], entries) == []

    def test_catch_all_does_not_count_as_owned(self):
        entries = [Entry('*', ('@canonical/maintainers',))]
        assert check_codeowners.find_unowned_dirs(['apt'], entries) == ['apt']

    def test_entry_without_owner_does_not_count(self):
        entries = [Entry('/apt/', ())]
        assert check_codeowners.find_unowned_dirs(['apt'], entries) == ['apt']

    def test_parent_dir_entry_does_not_own_child(self):
        # `/interfaces/` (the fallback) must not be treated as owning a specific interface.
        entries = [Entry('/interfaces/', ('@canonical/maintainers',))]
        unowned = check_codeowners.find_unowned_dirs(['interfaces/foo'], entries)
        assert unowned == ['interfaces/foo']

    def test_trailing_slash_directory_argument(self):
        entries = [Entry('/apt/', ('@canonical/team',))]
        assert check_codeowners.find_unowned_dirs(['/apt/'], entries) == []
