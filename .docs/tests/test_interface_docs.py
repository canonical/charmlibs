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

"""Unit tests for the interface_docs Sphinx fallback extension."""

from __future__ import annotations

import types
import typing

import interface_docs

if typing.TYPE_CHECKING:
    import pathlib

    import sphinx.application


def _app(confdir: pathlib.Path) -> sphinx.application.Sphinx:
    """A minimal stand-in for the Sphinx app: ``_fallback`` only reads ``confdir``."""
    return typing.cast('sphinx.application.Sphinx', types.SimpleNamespace(confdir=str(confdir)))


def test_fallback_writes_placeholder_when_dir_missing(tmp_path: pathlib.Path):
    """The reference/interfaces directory and placeholder are created if missing."""
    interface_docs._fallback(_app(tmp_path))

    placeholder = tmp_path / 'reference' / 'interfaces' / 'placeholder.md'
    assert placeholder.exists()
    assert placeholder.read_text() == '# Temporary TOC placeholder'


def test_fallback_keeps_existing_placeholder(tmp_path: pathlib.Path):
    """An existing placeholder is not overwritten."""
    ref_dir = tmp_path / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True)
    (ref_dir / 'placeholder.md').write_text('existing')

    interface_docs._fallback(_app(tmp_path))

    assert (ref_dir / 'placeholder.md').read_text() == 'existing'


def test_fallback_skips_placeholder_when_content_exists(tmp_path: pathlib.Path):
    """No placeholder is written when the preprocessor has generated pages."""
    ref_dir = tmp_path / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True)
    (ref_dir / 'foo.md').write_text('generated')

    interface_docs._fallback(_app(tmp_path))

    assert not (ref_dir / 'placeholder.md').exists()


def test_fallback_removes_stale_placeholder(tmp_path: pathlib.Path):
    """A leftover placeholder is removed when generated pages exist."""
    ref_dir = tmp_path / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True)
    (ref_dir / 'foo.md').write_text('generated')
    (ref_dir / 'placeholder.md').write_text('stale')

    interface_docs._fallback(_app(tmp_path))

    assert not (ref_dir / 'placeholder.md').exists()
    assert (ref_dir / 'foo.md').read_text() == 'generated'
