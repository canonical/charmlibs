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

# ruff: noqa: D103 (function docstrings)

"""Unit tests for the extract_changelog script."""

from __future__ import annotations

import typing

import extract_changelog
import pytest

if typing.TYPE_CHECKING:
    import pathlib

CHANGELOG = """\
# 1.3.0 - 2 June 2026

Widen the pattern argument.

Second paragraph.

# 1.2.1 - 6 February 2026

Only promise an `Iterator`.

# 1.2.0 - 1 January 2026

Require Python 3.10.
"""


def test_first_section():
    section = extract_changelog.extract(CHANGELOG, '1.3.0')
    assert section == 'Widen the pattern argument.\n\nSecond paragraph.'


def test_middle_section():
    section = extract_changelog.extract(CHANGELOG, '1.2.1')
    assert section == 'Only promise an `Iterator`.'


def test_last_section_runs_to_end_of_file():
    section = extract_changelog.extract(CHANGELOG, '1.2.0')
    assert section == 'Require Python 3.10.'


def test_missing_version():
    assert extract_changelog.extract(CHANGELOG, '9.9.9') is None


def test_version_is_matched_exactly_not_by_prefix():
    # '1.2' must not match the '1.2.1' or '1.2.0' headings.
    assert extract_changelog.extract(CHANGELOG, '1.2') is None


def test_post_release_version():
    text = '# 1.3.0.post0 - 16 June 2026\n\nUpdate project URLs.\n'
    assert extract_changelog.extract(text, '1.3.0.post0') == 'Update project URLs.'


def test_heading_without_a_date():
    text = '# 1.0.0\n\nFirst release.\n'
    assert extract_changelog.extract(text, '1.0.0') == 'First release.'


def test_subheadings_are_kept():
    text = '# 2.0.0 - 1 January 2026\n\n## Fixes\n\nA fix.\n\n# 1.0.0 - 1 January 2025\n\nOld.\n'
    assert extract_changelog.extract(text, '2.0.0') == '## Fixes\n\nA fix.'


# The interfaces packages open with a prose H1 and put versions at H2.
def test_extract_h2_versions_under_a_prose_h1():
    text = (
        '# Changelog\n\nAll notable changes are documented here.\n\n'
        '## 1.1.0 - 2 June 2026\n\nsecond\n\n'
        '## 1.0.0 - 1 June 2026\n\nfirst\n'
    )
    assert extract_changelog.extract(text, '1.1.0') == 'second'
    assert extract_changelog.extract(text, '1.0.0') == 'first'


# otlp and sloth follow Keep a Changelog, which brackets the version.
def test_extract_keep_a_changelog_bracketed_version():
    text = (
        '# Changelog\n\nThe format is based on Keep a Changelog.\n\n'
        '## [0.5.0] - 2026-01-02\n\n### Updated\n\n- newer\n\n'
        '## [0.4.0] - 2026-01-01\n\n- older\n'
    )
    got = extract_changelog.extract(text, '0.5.0')
    assert got is not None
    assert '- newer' in got
    assert '- older' not in got


# A subheading inside a version's section must not end it.
def test_extract_keeps_deeper_subheadings():
    text = '## [0.5.0] - 2026-01-02\n\n### Added\n\n- a\n\n### Fixed\n\n- b\n\n## [0.4.0]\n\nold\n'
    got = extract_changelog.extract(text, '0.5.0')
    assert got is not None
    assert '### Added' in got
    assert '### Fixed' in got
    assert 'old' not in got


# The prose heading must not be picked up as part of a version's section.
def test_extract_does_not_include_the_prose_heading():
    text = '# Changelog\n\nprose\n\n## 1.0.0 - 1 June 2026\n\nreal\n'
    assert extract_changelog.extract(text, '1.0.0') == 'real'


# A migration example in a breaking-change entry contains Python comments,
# which start with the same character as a heading.
def test_a_fenced_code_block_does_not_end_the_section():
    text = (
        '# 2.0.0 - 31 August 2026\n\n'
        'Breaking change. Migrate like this:\n\n'
        '```python\n# Before\nsnap.add("foo")\n# After\nsnap.install("foo")\n```\n\n'
        'Also fixed a leak.\n\n'
        '# 1.0.0 - 1 August 2026\n\nFirst release.\n'
    )
    got = extract_changelog.extract(text, '2.0.0')
    assert got is not None
    assert '# Before' in got
    assert got.endswith('Also fixed a leak.')
    # The fence is closed: notes ending mid-block render as a broken block.
    assert got.count('```') == 2
    # And the next version is still bounded correctly.
    assert extract_changelog.extract(text, '1.0.0') == 'First release.'


@pytest.mark.parametrize('fence', ['```', '~~~~'])
def test_both_fence_characters_are_honoured(fence: str):
    text = f'# 1.0.0\n\n{fence}\n# not a heading\n{fence}\n\ntail\n'
    got = extract_changelog.extract(text, '1.0.0')
    assert got is not None
    assert got.endswith('tail')


def test_main_prints_the_section(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]):
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text(CHANGELOG, encoding='utf-8')

    assert extract_changelog.main([str(changelog), '1.2.1']) == 0

    assert capsys.readouterr().out.strip() == extract_changelog.extract(CHANGELOG, '1.2.1')


def test_main_reports_a_missing_version(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
):
    """The whole safety argument is that the caller notices, so check it does."""
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text(CHANGELOG, encoding='utf-8')

    assert extract_changelog.main([str(changelog), '9.9.9']) == 1

    captured = capsys.readouterr()
    assert captured.out == ''
    assert '9.9.9' in captured.err
    assert str(changelog) in captured.err
