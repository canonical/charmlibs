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

"""Unit tests for the diataxis preprocessor script."""

from __future__ import annotations

import pathlib

import diataxis_preprocessor as pp
import pytest

# --- _build_sphinx_map ---


def test_build_sphinx_map_tutorial(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Tutorial files appear in the sphinx map."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_DOCS_DIR', tmp_path / '.docs')
    (tmp_path / '.docs').mkdir()
    packages: list[dict[str, object]] = [
        {'path': 'mylib', 'docs': {'tutorials': ['docs/tutorial.md']}},
    ]
    m = pp._build_sphinx_map(packages)
    assert m[pathlib.PurePath('mylib/docs/tutorial.md')] == '/tutorials/charmlibs/mylib/tutorial'


def test_build_sphinx_map_interface_version_readme(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    """Interface version READMEs map to /reference/interfaces/{name}/v{N}."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_DOCS_DIR', tmp_path / '.docs')
    (tmp_path / '.docs').mkdir()
    v1_dir = tmp_path / 'interfaces' / 'tls-certificates' / 'interface' / 'v1'
    v1_dir.mkdir(parents=True)
    (v1_dir / 'README.md').touch()
    packages: list[dict[str, object]] = [
        {'path': 'interfaces/tls-certificates', 'docs': {}},
    ]
    m = pp._build_sphinx_map(packages)
    assert (
        m[pathlib.PurePath('interfaces/tls-certificates/interface/v1/README.md')]
        == '/reference/interfaces/tls-certificates/v1'
    )


# --- _extract_h1 ---


def test_extract_h1_md():
    assert pp._extract_h1('# Getting Started\n\nText.\n', pathlib.Path('tutorial.md')) == (
        'Getting Started'
    )


def test_extract_h1_md_no_heading():
    with pytest.raises(ValueError, match=r'tutorial\.md'):
        pp._extract_h1('No heading here.\n', pathlib.Path('tutorial.md'))


def test_extract_h1_rst():
    assert pp._extract_h1('My Title\n========\n\nText.\n', pathlib.Path('tutorial.rst')) == (
        'My Title'
    )


def test_extract_h1_rst_no_heading():
    with pytest.raises(ValueError, match=r'tutorial\.rst'):
        pp._extract_h1('No heading here.\n', pathlib.Path('tutorial.rst'))


# --- _prefix_h1 ---


def test_prefix_h1_md():
    content = '# Getting Started\n\nSome text.\n'
    result = pp._prefix_h1(content, 'tls-certificates', '.md')
    assert result.startswith('# tls-certificates: Getting Started\n')


def test_prefix_h1_md_preserves_rest():
    content = '# Title\n\n## Subtitle\n\nBody.\n'
    result = pp._prefix_h1(content, 'mylib', '.md')
    assert result == '# mylib: Title\n\n## Subtitle\n\nBody.\n'


def test_prefix_h1_md_only_first():
    content = '# First\n\n# Second\n'
    result = pp._prefix_h1(content, 'lib', '.md')
    assert result == '# lib: First\n\n# Second\n'


def test_prefix_h1_rst():
    content = 'Getting Started\n================\n\nSome text.\n'
    result = pp._prefix_h1(content, 'tls-certificates', '.rst')
    expected_title = 'tls-certificates: Getting Started'
    lines = result.split('\n')
    assert lines[0] == expected_title
    assert lines[1] == '=' * len(expected_title)


# --- _rewrite_links ---


def test_rewrite_links_known_doc(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Relative link to a file in the sphinx map becomes a Sphinx path."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    # Target file must exist for resolve() to produce a consistent path.
    target = tmp_path / 'pkg' / 'docs' / 'how-to' / 'deploy.md'
    target.parent.mkdir(parents=True)
    target.touch()
    sphinx_map = {pathlib.PurePath('pkg/docs/how-to/deploy.md'): '/how-to/charmlibs/pkg/deploy'}
    content = 'See [guide](how-to/deploy.md) for details.'
    result = pp._rewrite_links(content, source, sphinx_map)
    assert result == 'See [guide](/how-to/charmlibs/pkg/deploy) for details.'


def test_rewrite_links_with_anchor(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Anchors are preserved after rewriting."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    target = tmp_path / 'pkg' / 'docs' / 'how-to' / 'deploy.md'
    target.parent.mkdir(parents=True)
    target.touch()
    sphinx_map = {pathlib.PurePath('pkg/docs/how-to/deploy.md'): '/how-to/charmlibs/pkg/deploy'}
    content = 'See [step 2](how-to/deploy.md#step-2).'
    result = pp._rewrite_links(content, source, sphinx_map)
    assert result == 'See [step 2](/how-to/charmlibs/pkg/deploy#step-2).'


def test_rewrite_links_unknown_file_github(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    """Relative link to a non-doc file falls back to GitHub URL."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_REPO_MAIN_URL', 'https://github.com/canonical/charmlibs/blob/main')
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    target = tmp_path / 'pkg' / 'src' / 'mod.py'
    target.parent.mkdir(parents=True)
    target.touch()
    content = 'See [source](../src/mod.py).'
    result = pp._rewrite_links(content, source, {})
    assert 'https://github.com/canonical/charmlibs/blob/main/pkg/src/mod.py' in result


def test_rewrite_links_preserves_http():
    """Absolute HTTP(S) links are left unchanged."""
    content = 'See [docs](https://example.com/page) for details.'
    result = pp._rewrite_links(content, pathlib.Path('/fake/source.md'), {})
    assert result == content


def test_rewrite_links_image_github(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Image links to non-doc files fall back to GitHub URL."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_REPO_MAIN_URL', 'https://github.com/canonical/charmlibs/blob/main')
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    target = tmp_path / 'pkg' / 'docs' / 'images' / 'arch.png'
    target.parent.mkdir(parents=True)
    target.touch()
    content = '![diagram](images/arch.png)'
    result = pp._rewrite_links(content, source, {})
    assert 'https://github.com/canonical/charmlibs/blob/main/pkg/docs/images/arch.png' in result


def test_rewrite_links_outside_repo_raises(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    """Link resolving outside the repo root raises ValueError."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path / 'repo')
    source = tmp_path / 'repo' / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    content = 'See [bad](../../../../etc/passwd).'
    with pytest.raises(ValueError):
        pp._rewrite_links(content, source, {})


# --- _copy_category ---


def test_copy_category_tutorial(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    source = tmp_path / 'lib' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    source.write_text('# My Tutorial\n\nContent.\n')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    entries = pp._copy_category([source], pathlib.PurePath('mylib'), 'tutorials', {})
    out = docs_dir / 'tutorials' / 'charmlibs' / 'mylib' / 'tutorial.md'
    assert out.exists()
    assert out.read_text().startswith('# mylib: My Tutorial\n')
    assert entries == ['mylib: My Tutorial <charmlibs/mylib/tutorial>']


def test_copy_category(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    howto_dir = tmp_path / 'lib' / 'docs' / 'how-to'
    howto_dir.mkdir(parents=True)
    (howto_dir / 'deploy.md').write_text('# Deploy\n\nSteps.\n')
    (howto_dir / 'upgrade.md').write_text('# Upgrade\n\nSteps.\n')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    sources = sorted(howto_dir.glob('*.md'))
    entries = pp._copy_category(sources, pathlib.PurePath('mylib'), 'how-to', {})
    out_dir = docs_dir / 'how-to' / 'charmlibs' / 'mylib'
    assert (out_dir / 'deploy.md').exists()
    assert (out_dir / 'upgrade.md').exists()
    assert (out_dir / 'deploy.md').read_text().startswith('# mylib: Deploy\n')
    assert len(entries) == 2
    assert 'mylib: Deploy <charmlibs/mylib/deploy>' in entries


def test_copy_category_interface(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    expl_dir = tmp_path / 'lib' / 'docs' / 'explanation'
    expl_dir.mkdir(parents=True)
    (expl_dir / 'security.md').write_text('# Security\n')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    entries = pp._copy_category(
        [expl_dir / 'security.md'], pathlib.PurePath('interfaces/tls-certs'), 'explanation', {}
    )
    out = docs_dir / 'explanation' / 'charmlibs' / 'interfaces' / 'tls-certs' / 'security.md'
    assert out.exists()
    assert entries == ['tls-certs: Security <charmlibs/interfaces/tls-certs/security>']


def test_copy_category_empty_sources(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entries = pp._copy_category([], pathlib.PurePath('mylib'), 'how-to', {})
    assert entries == []
