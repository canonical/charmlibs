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

"""Unit tests for the interface preprocessor script."""

from __future__ import annotations

import json
import typing

import interface_preprocessor as ip

if typing.TYPE_CHECKING:
    import pathlib

    import pytest

# --- _main ---


def _fake_ls(interfaces: list[str]) -> typing.Callable[..., str]:
    """A stand-in for ``subprocess.check_output`` returning the given interfaces."""

    def check_output(*args: object, **kwargs: object) -> str:
        return json.dumps(interfaces)

    return check_output


def test_main_writes_index_and_version_pages(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    """Index stubs and rewritten READMEs are written for each interface."""
    docs_dir = tmp_path / 'docs_site'
    ref_dir = docs_dir / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True)
    (ref_dir / 'placeholder.md').write_text('# Temporary TOC placeholder')
    v1_dir = tmp_path / 'interfaces' / 'foo' / 'interface' / 'v1'
    v1_dir.mkdir(parents=True)
    (v1_dir / 'README.md').write_text('# Foo v1\n\nSee [schema](schema.md).\n')
    monkeypatch.setattr(ip, '_DOCS_DIR', docs_dir)
    monkeypatch.setattr(ip, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(ip.subprocess, 'check_output', _fake_ls(['interfaces/foo']))

    ip._main()

    assert not (ref_dir / 'placeholder.md').exists()
    index = (ref_dir / 'foo.md').read_text()
    assert index.startswith('(interfaces-foo)=\n# foo\n')
    assert 'foo/*' in index
    v1 = (ref_dir / 'foo' / 'v1.md').read_text()
    assert v1.startswith('(interfaces-foo-v1)=\n# Foo v1\n')


def test_main_removes_placeholder(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """The fallback placeholder is removed when the preprocessor runs."""
    docs_dir = tmp_path / 'docs_site'
    ref_dir = docs_dir / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True)
    (ref_dir / 'placeholder.md').write_text('# Temporary TOC placeholder')
    monkeypatch.setattr(ip, '_DOCS_DIR', docs_dir)
    monkeypatch.setattr(ip, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(ip.subprocess, 'check_output', _fake_ls([]))

    ip._main()

    assert not (ref_dir / 'placeholder.md').exists()


# --- _generate_interface_docs ---


def test_generate_index_stub(tmp_path: pathlib.Path):
    """The index stub has a hyphenated label and a glob toctree."""
    interface_dir = tmp_path / 'interfaces' / 'tls_certificates'
    interface_dir.mkdir(parents=True)
    ref_dir = tmp_path / 'ref'
    ref_dir.mkdir()

    ip._generate_interface_docs(interface_dir=interface_dir, ref_dir=ref_dir)

    index = (ref_dir / 'tls_certificates.md').read_text()
    assert index.startswith('(interfaces-tls-certificates)=\n# tls_certificates\n')
    assert 'tls_certificates/*' in index


def test_generate_rewrites_version_readme_links(tmp_path: pathlib.Path):
    """Relative links in version READMEs become absolute GitHub URLs."""
    v2_dir = tmp_path / 'interfaces' / 'foo' / 'interface' / 'v2'
    v2_dir.mkdir(parents=True)
    (v2_dir / 'README.md').write_text(
        '# Foo v2\n\nSee [schema](schema.md) and [docs](https://example.com/).\n'
    )
    ref_dir = tmp_path / 'ref'
    ref_dir.mkdir()

    ip._generate_interface_docs(interface_dir=v2_dir.parent.parent, ref_dir=ref_dir)

    v2 = (ref_dir / 'foo' / 'v2.md').read_text()
    assert v2.startswith('(interfaces-foo-v2)=\n# Foo v2\n')
    base = f'{ip._REPO_MAIN_URL}/interfaces/foo/interface/v2'
    assert f'[schema]({base}/schema.md)' in v2
    assert '[docs](https://example.com/)' in v2


def test_generate_no_interface_dir(tmp_path: pathlib.Path):
    """Interfaces without an interface/ directory get an index stub only."""
    interface_dir = tmp_path / 'interfaces' / 'foo'
    interface_dir.mkdir(parents=True)
    ref_dir = tmp_path / 'ref'
    ref_dir.mkdir()

    ip._generate_interface_docs(interface_dir=interface_dir, ref_dir=ref_dir)

    assert (ref_dir / 'foo.md').exists()
    # The per-interface directory is created, but contains no version pages.
    assert list((ref_dir / 'foo').glob('*.md')) == []


def test_generate_skips_unchanged_files(tmp_path: pathlib.Path):
    """Files whose content hasn't changed are not rewritten."""
    interface_dir = tmp_path / 'interfaces' / 'foo'
    interface_dir.mkdir(parents=True)
    ref_dir = tmp_path / 'ref'
    ref_dir.mkdir()
    index = ref_dir / 'foo.md'

    ip._generate_interface_docs(interface_dir=interface_dir, ref_dir=ref_dir)
    mtime = index.stat().st_mtime_ns

    ip._generate_interface_docs(interface_dir=interface_dir, ref_dir=ref_dir)

    assert index.stat().st_mtime_ns == mtime


# --- _rewrite_links ---


def test_rewrite_links_relative():
    content = 'See [the schema](schema.md) for details.'
    result = ip._rewrite_links(content, 'https://example.com/base')
    assert result == 'See [the schema](https://example.com/base/schema.md) for details.'


def test_rewrite_links_preserves_http():
    content = 'See [docs](https://example.com/page) and [other](http://example.com/).'
    assert ip._rewrite_links(content, 'https://example.com/base') == content


# --- _write_if_needed ---


def test_write_if_needed_writes_missing(tmp_path: pathlib.Path):
    path = tmp_path / 'out.md'
    ip._write_if_needed(path=path, content='content')
    assert path.read_text() == 'content'


def test_write_if_needed_skips_identical(tmp_path: pathlib.Path):
    path = tmp_path / 'out.md'
    path.write_text('content')
    mtime = path.stat().st_mtime_ns
    ip._write_if_needed(path=path, content='content')
    assert path.stat().st_mtime_ns == mtime


def test_write_if_needed_rewrites_different(tmp_path: pathlib.Path):
    path = tmp_path / 'out.md'
    path.write_text('old')
    ip._write_if_needed(path=path, content='new')
    assert path.read_text() == 'new'
