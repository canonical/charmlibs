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
Path = check_codeowners.Path


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

    def test_drops_wildcard_patterns(self):
        text = '* @canonical/team\n/*.md @canonical/team\n/foo/[abc] @t\n/apt/ @canonical/team\n'
        # Only the anchored, wildcard-free entry survives.
        assert check_codeowners.parse_codeowners(text) == [
            Entry(pattern='/apt/', owners=('@canonical/team',))
        ]

    def test_empty(self):
        assert check_codeowners.parse_codeowners('') == []


class TestEntryTarget:
    @pytest.mark.parametrize(
        ('pattern', 'expected'),
        [
            # The leading slash is stripped; the trailing slash is preserved verbatim.
            ('/apt/', 'apt/'),
            ('/apt', 'apt'),
            ('/interfaces/foo/interface/', 'interfaces/foo/interface/'),
            ('/interfaces/foo/ruff.toml', 'interfaces/foo/ruff.toml'),
        ],
    )
    def test_path_patterns(self, pattern: str, expected: str):
        assert check_codeowners.entry_target(pattern) == expected


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

    def test_directory_entry_without_trailing_slash_is_orphan(self, tmp_path: pathlib.Path):
        (tmp_path / 'apt').mkdir()
        entries = [Entry('/apt', ('@canonical/team',))]  # missing the trailing slash
        assert check_codeowners.find_orphan_entries(entries, tmp_path) == ['/apt']

    def test_file_entry_with_trailing_slash_is_orphan(self, tmp_path: pathlib.Path):
        (tmp_path / 'README.md').touch()
        entries = [Entry('/README.md/', ('@canonical/team',))]  # stray trailing slash on a file
        assert check_codeowners.find_orphan_entries(entries, tmp_path) == ['/README.md/']


class TestBuildPaths:
    def test_top_level_and_interface_children(self):
        files = [
            'README.md',
            'apt/pyproject.toml',
            'apt/src/__init__.py',
            'interfaces/index.json',
            'interfaces/foo/ruff.toml',
            'interfaces/foo/interface/v0/schema.py',
        ]
        assert check_codeowners.build_paths(files) == [
            Path('README.md', ()),
            Path('apt/', ('apt/pyproject.toml', 'apt/src/')),
            Path('interfaces/', ('interfaces/foo/', 'interfaces/index.json')),
            Path('interfaces/foo/', ('interfaces/foo/interface/', 'interfaces/foo/ruff.toml')),
            Path('interfaces/index.json', ()),
        ]

    def test_directories_end_with_slash(self):
        [apt] = check_codeowners.build_paths(['apt/x.py'])
        assert apt.path == 'apt/'

    def test_files_have_no_children(self):
        [readme] = check_codeowners.build_paths(['README.md'])
        assert readme == Path('README.md', ())

    def test_empty(self):
        assert check_codeowners.build_paths([]) == []


class TestFindUnownedDirs:
    def test_path_with_own_entry_passes(self):
        entries = [Entry('/apt/', ('@canonical/team',))]
        paths = [Path('apt/', ('apt/src/',))]
        assert check_codeowners.find_unowned_dirs(entries, paths) == []

    def test_directory_entry_must_match_trailing_slash(self):
        # A directory entry without a trailing slash doesn't match the slashed path verbatim.
        entries = [Entry('/apt', ('@canonical/team',))]
        paths = [Path('apt/', ('apt/src/',))]
        assert check_codeowners.find_unowned_dirs(entries, paths) == ['apt/']

    def test_all_children_owned_passes(self):
        # Split interface entries: the dir itself has no entry, but each child does.
        entries = [
            Entry('/interfaces/foo/interface/', ('@canonical/team',)),
            Entry('/interfaces/foo/ruff.toml', ('@canonical/team',)),
        ]
        children = ('interfaces/foo/interface/', 'interfaces/foo/ruff.toml')
        paths = [Path('interfaces/foo/', children)]
        assert check_codeowners.find_unowned_dirs(entries, paths) == []

    def test_all_children_disowned_passes(self):
        # Children with ownerless entries are explicitly disowned, which satisfies the parent.
        entries = [Entry('/foo/a', ()), Entry('/foo/b', ())]
        paths = [Path('foo/', ('foo/a', 'foo/b'))]
        assert check_codeowners.find_unowned_dirs(entries, paths) == []

    def test_some_children_unowned_is_unowned(self):
        entries = [Entry('/interfaces/foo/interface/', ('@canonical/team',))]
        children = ('interfaces/foo/interface/', 'interfaces/foo/ruff.toml')
        paths = [Path('interfaces/foo/', children)]
        assert check_codeowners.find_unowned_dirs(entries, paths) == ['interfaces/foo/']

    def test_disowned_path_passes(self):
        # An ownerless entry for the path itself counts (e.g. interfaces/index.json).
        entries = [Entry('/interfaces/index.json', ())]
        paths = [Path('interfaces/index.json', ())]
        assert check_codeowners.find_unowned_dirs(entries, paths) == []

    def test_rule_is_not_recursive(self):
        # A grandchild entry must NOT satisfy a child; `interfaces/foo/interface/` has no entry,
        # only its own child does, so `interfaces/foo/` is not owned.
        entries = [Entry('/interfaces/foo/interface/v0/', ('@canonical/team',))]
        paths = [Path('interfaces/foo/', ('interfaces/foo/interface/',))]
        assert check_codeowners.find_unowned_dirs(entries, paths) == ['interfaces/foo/']

    def test_no_entries_means_unowned(self):
        # The catch-all `*` is dropped by the parser, so find_unowned_dirs never sees it.
        paths = [Path('apt/', ('apt/src/',))]
        assert check_codeowners.find_unowned_dirs([], paths) == ['apt/']

    def test_parent_dir_entry_does_not_own_child(self):
        # `/interfaces/` (the fallback) must not be treated as owning a specific interface.
        entries = [Entry('/interfaces/', ('@canonical/maintainers',))]
        paths = [Path('interfaces/foo/', ('interfaces/foo/ruff.toml',))]
        assert check_codeowners.find_unowned_dirs(entries, paths) == ['interfaces/foo/']

    def test_file_needs_own_entry(self):
        entries = [Entry('/other', ('@canonical/team',))]
        paths = [Path('README.md', ())]
        assert check_codeowners.find_unowned_dirs(entries, paths) == ['README.md']

    def test_dir_with_no_children_needs_own_entry(self):
        entries = [Entry('/other/', ('@canonical/team',))]
        paths = [Path('apt/', ())]
        assert check_codeowners.find_unowned_dirs(entries, paths) == ['apt/']
