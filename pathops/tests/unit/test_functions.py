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

"""Tests that don't use a real Pebble to test helper functions."""

from __future__ import annotations

import pathlib
import typing

import ops
import pytest
from ops import pebble

import utils
from charmlibs.pathops import ContainerPath, LocalPath, ensure_contents
from charmlibs.pathops._functions import _get_fileinfo

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


@pytest.mark.parametrize(
    ('mock', 'error'),
    (
        (utils.raise_connection_error, pebble.ConnectionError),
        (utils.raise_unknown_api_error, pebble.APIError),
    ),
)
def test_get_fileinfo_reraises_unhandled_pebble_errors(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
    mock: Callable[[Any], None],
    error: type[Exception],
):
    monkeypatch.setattr(container, 'list_files', mock)
    with pytest.raises(error):
        _get_fileinfo(ContainerPath('/', container=container))


@pytest.mark.parametrize('path_type', [str, pathlib.Path, LocalPath])
def test_ensure_contents_matcher_replaces(
    tmp_path: pathlib.Path,
    path_type: type[str] | type[pathlib.Path] | type[LocalPath],
):
    path = tmp_path / 'config'
    path.write_text('user=root\nport=80\n')
    changed = ensure_contents(
        path_type(path),
        'user=guest',
        matcher=r'^user=.*$',
    )
    assert changed
    assert path.read_text() == 'user=guest\nport=80\n'
    # idempotent
    assert not ensure_contents(path_type(path), 'user=guest', matcher=r'^user=.*$')


def test_ensure_contents_matcher_replaces_all_matches(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('user=a\nuser=b\n')
    changed = ensure_contents(path, 'user=c', matcher=r'^user=.*$')
    assert changed
    assert path.read_text() == 'user=c\nuser=c\n'


def test_ensure_contents_matcher_appends_when_no_match(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('port=80\n')
    changed = ensure_contents(path, 'user=guest', matcher=r'^user=.*$', no_match='append')
    assert changed
    assert path.read_text() == 'port=80\nuser=guest\n'
    # appending an already-present line is a no-op
    assert not ensure_contents(path, 'user=guest', matcher=r'^user=.*$', no_match='append')


def test_ensure_contents_matcher_append_terminates_unterminated_file(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('port=80')  # no trailing newline
    changed = ensure_contents(path, 'user=guest', matcher=r'^user=.*$', no_match='append')
    assert changed
    assert path.read_text() == 'port=80\nuser=guest\n'


def test_ensure_contents_matcher_no_match_leaves_file_unchanged(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('port=80\n')
    assert not ensure_contents(path, 'user=guest', matcher=r'^user=.*$')
    assert path.read_text() == 'port=80\n'


def test_ensure_contents_matcher_no_match_replace(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('port=80\n')
    changed = ensure_contents(path, 'user=guest', matcher=r'^user=.*$', no_match='replace')
    assert changed
    assert path.read_text() == 'user=guest\n'


def test_ensure_contents_matcher_creates_missing_file(tmp_path: pathlib.Path):
    path = tmp_path / 'subdir' / 'config'
    changed = ensure_contents(path, 'user=guest', matcher=r'^user=.*$')
    assert changed
    assert path.read_text() == 'user=guest\n'


def test_ensure_contents_matcher_accepts_pattern(tmp_path: pathlib.Path):
    import re

    path = tmp_path / 'config'
    path.write_text('user=root\n')
    changed = ensure_contents(path, 'user=guest', matcher=re.compile(r'^user=.*$'))
    assert changed
    assert path.read_text() == 'user=guest\n'


def test_ensure_contents_matcher_spans_multiple_lines(tmp_path: pathlib.Path):
    import re

    path = tmp_path / 'config'
    path.write_text('# begin\nold=1\nold=2\n# end\nport=80\n')
    matcher = re.compile(r'# begin\n.*\n# end', re.DOTALL)
    changed = ensure_contents(path, '# begin\nnew=3\n# end', matcher=matcher)
    assert changed
    assert path.read_text() == '# begin\nnew=3\n# end\nport=80\n'
    # idempotent
    assert not ensure_contents(path, '# begin\nnew=3\n# end', matcher=matcher)


def test_ensure_contents_matcher_pattern_without_multiline(tmp_path: pathlib.Path):
    import re

    # without re.MULTILINE, ^ only matches at the start of the file
    path = tmp_path / 'config'
    path.write_text('port=80\nuser=root\n')
    changed = ensure_contents(
        path,
        'user=guest',
        matcher=re.compile(r'^user=.*$'),
        no_match='append',
    )
    assert changed
    # no match, so source was appended
    assert path.read_text() == 'port=80\nuser=root\nuser=guest\n'


def test_ensure_contents_matcher_supports_backreferences(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('user=root:admin\nport=80\n')
    changed = ensure_contents(path, r'user=\1:wheel', matcher=r'^user=(\S+):(\S+)$')
    assert changed
    assert path.read_text() == 'user=root:wheel\nport=80\n'


def test_ensure_contents_matcher_named_backreferences(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('user=root\n')
    changed = ensure_contents(path, r'user=\g<name> (managed)', matcher=r'^user=(?P<name>\S+)$')
    assert changed
    assert path.read_text() == 'user=root (managed)\n'


def test_ensure_contents_matcher_backrefs_no_match_raises(tmp_path: pathlib.Path):
    path = tmp_path / 'config'
    path.write_text('port=80\n')
    with pytest.raises(ValueError, match='no match'):
        ensure_contents(path, r'user=\1', matcher=r'^user=(\S+)$', no_match='append')


def test_ensure_contents_matcher_backrefs_no_match_ignored(tmp_path: pathlib.Path):
    # with the default ignore behaviour there is nothing to expand, so no error
    path = tmp_path / 'config'
    path.write_text('port=80\n')
    assert not ensure_contents(path, r'user=\1', matcher=r'^user=(\S+)$')
    assert path.read_text() == 'port=80\n'


@pytest.mark.parametrize('newline', ['\n', r'\n'])
def test_ensure_contents_matcher_source_newline_raises(tmp_path: pathlib.Path, newline: str):
    path = tmp_path / 'config'
    path.write_text('user=root\n')
    with pytest.raises(ValueError, match='must not end with a newline'):
        ensure_contents(path, 'user=guest' + newline, matcher=r'^user=.*$')
