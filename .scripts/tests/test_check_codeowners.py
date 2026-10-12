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
Path = pathlib.Path


def _children(*files: str) -> dict[pathlib.Path, list[pathlib.Path]]:
    """Build the parent -> children map from repo-relative file path strings."""
    return check_codeowners.map_children([Path(f) for f in files])


def _entries(*patterns: str) -> dict[pathlib.Path, str]:
    """Build a `{target: pattern}` entries dict from CODEOWNERS pattern strings."""
    return {Path(pattern.strip('/')): pattern for pattern in patterns}


# The real repo always has a top-level `interfaces/` directory (with `interfaces/foo`), so
# `check` indexes into both unconditionally. These provide a fully-owned baseline that tests
# extend, so a test only needs to specify the paths and entries it actually exercises.
_BASE_FILES = ('interfaces/foo/ruff.toml',)
_BASE_PATTERNS = ('/interfaces/', '/interfaces/foo/')


class TestParseCodeowners:
    def test_keys_by_repo_relative_target(self):
        text = '/apt/ @canonical/team  # trailing comment\n'
        assert check_codeowners.parse_codeowners(text) == {Path('apt'): '/apt/'}

    def test_ignores_comments_and_blanks(self):
        text = '# a comment\n\n/apt/ @canonical/team\n'
        assert check_codeowners.parse_codeowners(text) == {Path('apt'): '/apt/'}

    def test_keeps_pattern_verbatim(self):
        text = '/foo/ @canonical/one @canonical/two\n'
        assert check_codeowners.parse_codeowners(text)[Path('foo')] == '/foo/'

    def test_entry_without_owner(self):
        text = '/interfaces/index.json\n'
        assert check_codeowners.parse_codeowners(text) == {
            Path('interfaces/index.json'): '/interfaces/index.json'
        }

    def test_drops_wildcard_patterns(self):
        text = '* @canonical/team\n/*.md @canonical/team\n/foo/[abc] @t\n/apt/ @canonical/team\n'
        # Only the anchored, wildcard-free entry survives.
        assert check_codeowners.parse_codeowners(text) == {Path('apt'): '/apt/'}

    def test_empty(self):
        assert check_codeowners.parse_codeowners('') == {}


class TestMapChildren:
    def test_maps_parents_to_immediate_children(self):
        children = _children('README.md', 'apt/pyproject.toml', 'apt/src/__init__.py')
        assert children == {
            Path(): [Path('README.md'), Path('apt')],
            Path('apt'): [Path('apt/pyproject.toml'), Path('apt/src')],
            Path('apt/src'): [Path('apt/src/__init__.py')],
        }

    def test_files_are_not_keys(self):
        children = _children('README.md')
        assert children == {Path(): [Path('README.md')]}
        assert Path('README.md') not in children

    def test_empty(self):
        assert _children() == {}


class TestCheck:
    def _check(self, entries: dict[pathlib.Path, str], *files: str) -> list[str]:
        """Run `check` with a fully-owned `interfaces/` baseline plus the given entries/files."""
        return check_codeowners.check(
            {**_entries(*_BASE_PATTERNS), **entries},
            _children(*_BASE_FILES, *files),
        )

    def test_path_with_own_entry_passes(self):
        assert self._check(_entries('/apt/'), 'apt/src/x.py') == []

    def test_all_children_owned_passes(self):
        # Split interface entries: interfaces/bar has no entry, but each of its children does.
        entries = _entries('/interfaces/bar/interface/', '/interfaces/bar/ruff.toml')
        files = ('interfaces/bar/interface/v0/schema.py', 'interfaces/bar/ruff.toml')
        assert self._check(entries, *files) == []

    def test_top_level_file_needs_own_entry(self):
        # The unowned top-level README.md is reported.
        problems = self._check({}, 'README.md')
        assert problems == ['No explicit CODEOWNERS for: /README.md']

    def test_dir_with_unowned_child_is_reported(self):
        # interfaces/bar's ruff.toml lacks an entry, so bar is unowned.
        entries = _entries('/interfaces/bar/interface/')
        files = ('interfaces/bar/interface/v0/schema.py', 'interfaces/bar/ruff.toml')
        assert self._check(entries, *files) == [
            "No explicit CODEOWNERS for: /interfaces/bar/ (and its children aren't all owned)"
        ]

    def test_rule_is_not_recursive(self):
        # A grandchild entry must NOT satisfy a child; interfaces/bar/interface has no entry.
        entries = _entries('/interfaces/bar/interface/v0/')
        assert self._check(entries, 'interfaces/bar/interface/v0/schema.py') == [
            "No explicit CODEOWNERS for: /interfaces/bar/ (and its children aren't all owned)"
        ]

    def test_parent_dir_entry_does_not_own_child(self):
        # /interfaces/ owns the interfaces dir, but not a specific interface inside it.
        assert self._check({}, 'interfaces/bar/ruff.toml') == [
            "No explicit CODEOWNERS for: /interfaces/bar/ (and its children aren't all owned)"
        ]

    def test_missing_entry_target_is_reported(self):
        problems = self._check(_entries('/apt/', '/gone/'), 'apt/src/x.py')
        assert 'CODEOWNERS entry points at a missing path: /gone/' in problems

    def test_directory_entry_without_trailing_slash_is_reported(self):
        problems = self._check(_entries('/apt'), 'apt/src/x.py')  # missing trailing slash
        assert 'CODEOWNERS entry must have a trailing slash iff it is a dir: /apt' in problems

    def test_file_entry_with_trailing_slash_is_reported(self):
        problems = self._check(_entries('/README.md/'), 'README.md')  # stray trailing slash
        msg = 'CODEOWNERS entry must have a trailing slash iff it is a dir: /README.md/'
        assert msg in problems

    def test_unanchored_entry_is_reported(self):
        # A pattern without a leading slash is forbidden (parsed relative to the repo root).
        problems = self._check({Path('apt'): 'apt/'}, 'apt/src/x.py')
        assert 'CODEOWNERS entry must be anchored with a leading /: apt/' in problems
