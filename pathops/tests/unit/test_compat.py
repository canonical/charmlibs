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

"""Cross-check pathops polyfills against the stdlib on Python versions that provide it."""

from __future__ import annotations

import pathlib
import sys

import pytest

from charmlibs.pathops import _compat

if sys.version_info < (3, 13):
    pytest.skip('pathlib.PurePath.full_match added in Python 3.13', allow_module_level=True)
assert sys.version_info >= (3, 13)  # narrow for pyright


@pytest.mark.parametrize(
    ('path', 'pattern'),
    [
        ('/foo/bar.txt', '/foo/bar.txt'),
        ('/foo/bar.txt', '/foo/baz.txt'),
        ('/foo/bar.txt', 'bar.txt'),
        ('/foo/bar.txt', 'foo/bar.txt'),
        ('/other/bar.txt', 'foo/bar.txt'),
        ('/a/b/c.txt', '**/c.txt'),
        ('/a/b/c.txt', '**/b.txt'),
        ('foo/bar.txt', 'foo/bar.txt'),
        ('foo/bar.txt', '/foo/bar.txt'),
        ('/a/b/c/d.txt', '/a/**/d.txt'),
        ('/a/d.txt', '/a/**/d.txt'),
        ('/x.txt', '**'),
        ('/a/b', '/a/*'),
        ('/x.txt', '**/x.txt'),
        ('/x.txt', '**/*.txt'),
        ('a/b/c.txt', '**/c.txt'),
        ('/foo/bar', '**/bar'),
        ('/foo', '**/foo'),
        ('/foo/bar.txt', '**/foo/bar.txt'),
        ('/foo/bar.txt', '/**/bar.txt'),
        ('/foo/bar.txt', '/foo/**'),
        ('/foo/bar.txt', 'foo/**'),
        ('foo/bar.txt', '/**'),
        ('/', '**'),
        ('/', '/**'),
        ('foo', '**/foo'),
        ('a/foo', '**/foo'),
        ('a/b/foo', '**/foo'),
        ('/foo', '/**/foo'),
        ('/a/foo', '/**/foo'),
        ('/a/b/foo', '/**/foo'),
        ('foo', '**'),
        ('foo', 'foo/**'),
        ('foo/bar', 'foo/**'),
        ('a/b', '**/*'),
        ('a', '**/*'),
        ('a/b/c', '**/*/*'),
        ('/foo//bar', '/foo/bar'),
        ('/foo/./bar', '/foo/bar'),
        ('/foo/bar/', '/foo/bar'),
        ('/foo/bar', '/foo/bar/'),
        ('/a/b.txt', '/a/[bcd].txt'),
        ('/a/e.txt', '/a/[bcd].txt'),
        ('/a/b.txt', '/a/?.txt'),
        ('/a/bc.txt', '/a/?.txt'),
    ],
)
def test_full_match_matches_pathlib(path: str, pattern: str):
    expected = pathlib.PurePosixPath(path).full_match(pattern)
    assert _compat.full_match(path, pattern) == expected


@pytest.mark.parametrize(
    ('path', 'pattern'),
    [
        ('/FOO/bar.txt', '/foo/bar.txt'),
        ('/FOO/BAR.TXT', '/foo/bar.txt'),
        ('/Foo/Bar.txt', '/foo/bar.txt'),
        ('/a/B/c.TXT', '**/c.txt'),
        ('/a/b/c.txt', '/A/B/*.TXT'),
        ('/foo/BAR.TXT', '/foo/bar.txt'),
        ('/foo/bar.txt', '/foo/bar.txt'),
    ],
)
@pytest.mark.parametrize('case_sensitive', [None, True, False])
def test_full_match_case_sensitive_matches_pathlib(
    path: str, pattern: str, case_sensitive: bool | None
):
    expected = pathlib.PurePosixPath(path).full_match(pattern, case_sensitive=case_sensitive)
    assert _compat.full_match(path, pattern, case_sensitive=case_sensitive) == expected
