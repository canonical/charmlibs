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

"""Unit tests for the diataxis_docs_fallback Sphinx extension."""

from __future__ import annotations

import types
import typing

import diataxis_docs_fallback as fallback

if typing.TYPE_CHECKING:
    import pathlib

    import sphinx.application

CATEGORIES = ('tutorials', 'how-to', 'explanation')


def _app(confdir: pathlib.Path) -> sphinx.application.Sphinx:
    """A minimal stand-in for the Sphinx app: ``_fallback`` only reads ``confdir``."""
    return typing.cast('sphinx.application.Sphinx', types.SimpleNamespace(confdir=str(confdir)))


def test_fallback_writes_empty_include_when_missing(tmp_path: pathlib.Path):
    """Fallback writes empty include files when preprocessor hasn't run."""
    for category in CATEGORIES:
        (tmp_path / category).mkdir()

    fallback._fallback(_app(tmp_path))

    for category in CATEGORIES:
        path = tmp_path / category / f'_lib-{category}.md'
        assert path.exists()
        assert path.read_text() == ''


def test_fallback_skips_when_include_exists(tmp_path: pathlib.Path):
    """Fallback does nothing when preprocessor has already run."""
    for category in CATEGORIES:
        (tmp_path / category).mkdir()
        (tmp_path / category / f'_lib-{category}.md').write_text('existing')

    fallback._fallback(_app(tmp_path))

    for category in CATEGORIES:
        path = tmp_path / category / f'_lib-{category}.md'
        assert path.read_text() == 'existing'
