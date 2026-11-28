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
import pytest

if typing.TYPE_CHECKING:
    import pathlib

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
    assert v1.startswith('(interfaces-foo-v1)=\n# `foo/v1`\n\nSee [schema](')
    assert '# Foo v1' not in v1


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


def test_main_fails_early_on_missing_readme(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    """A version directory without a README.md fails before anything is written."""
    docs_dir = tmp_path / 'docs_site'
    ref_dir = docs_dir / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True)
    (ref_dir / 'placeholder.md').write_text('# Temporary TOC placeholder')
    good = tmp_path / 'interfaces' / 'bar' / 'interface' / 'v0'
    good.mkdir(parents=True)
    (good / 'README.md').write_text('# Bar v0\n')
    for version in ('v0', 'v1'):
        (tmp_path / 'interfaces' / 'foo' / 'interface' / version).mkdir(parents=True)
    monkeypatch.setattr(ip, '_DOCS_DIR', docs_dir)
    monkeypatch.setattr(ip, '_REPO_ROOT', tmp_path)
    interfaces = ['interfaces/bar', 'interfaces/foo']
    monkeypatch.setattr(ip.subprocess, 'check_output', _fake_ls(interfaces))

    with pytest.raises(SystemExit) as exc_info:
        ip._main()

    message = str(exc_info.value.code)
    assert 'README.md' in message
    assert 'interfaces/foo/interface/v0/README.md' in message
    assert 'interfaces/foo/interface/v1/README.md' in message
    assert 'interfaces/bar' not in message
    # Nothing was written, and the placeholder is left for the fallback extension.
    assert sorted(p.name for p in ref_dir.iterdir()) == ['placeholder.md']


def test_main_fails_after_writing_pages_if_there_were_warnings(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    """A warning while generating the pages fails the script, once every page is written."""
    docs_dir = tmp_path / 'docs_site'
    ref_dir = docs_dir / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True)
    v0_dir = tmp_path / 'interfaces' / 'foo' / 'interface' / 'v0'
    v0_dir.mkdir(parents=True)
    (v0_dir / 'README.md').write_text('# Foo v0\n')
    (v0_dir / 'schema.py').write_text('')
    monkeypatch.setattr(ip, '_DOCS_DIR', docs_dir)
    monkeypatch.setattr(ip, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(ip.subprocess, 'check_output', _fake_ls(['interfaces/foo']))
    monkeypatch.setattr(ip, '_logger', ip._Logger())

    def load_schemas(root: pathlib.Path, schema_paths: list[str]) -> dict[str, typing.Any]:
        assert schema_paths == ['interfaces/foo/interface/v0/schema.py']
        ip._logger.warning('Could not load the interface schemas: %s', 'no uv')
        return {}

    monkeypatch.setattr(ip, '_load_schemas', load_schemas)

    with pytest.raises(SystemExit) as exc_info:
        ip._main()

    assert '1 warning(s)' in str(exc_info.value.code)
    assert (ref_dir / 'foo' / 'v0.md').read_text() == '(interfaces-foo-v0)=\n# `foo/v0`\n'


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
    assert v2.startswith('(interfaces-foo-v2)=\n# `foo/v2`\n')
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


def test_generate_orders_header_readme_and_relation_data(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ip, '_REPO_ROOT', tmp_path)
    v0_dir = tmp_path / 'interfaces' / 'foo' / 'interface' / 'v0'
    v0_dir.mkdir(parents=True)
    (v0_dir / 'README.md').write_text('# foo\n\n## Behavior\n\n[x](y.md)\n')
    (v0_dir / 'interface.yaml').write_text(
        'name: foo\nstatus: published\nlib: charmlibs.interfaces.foo\ndescription: |\n  Foo.\n'
    )
    ref_dir = tmp_path / 'ref'
    ref_dir.mkdir()
    databags: dict[str, typing.Any] = {
        'provider-app': {'properties': {'host': {'type': 'string'}}, 'type': 'object'}
    }

    ip._generate_interface_docs(
        interface_dir=v0_dir.parent.parent,
        ref_dir=ref_dir,
        schemas={'interfaces/foo/interface/v0/schema.py': databags},
        package_labels=frozenset({'charmlibs-interfaces-foo'}),
    )

    base = f'{ip._REPO_MAIN_URL}/interfaces/foo/interface/v0'
    assert (
        (ref_dir / 'foo' / 'v0.md')
        .read_text()
        .startswith(
            '(interfaces-foo-v0)=\n'
            '# `foo/v0`\n\n'
            'Foo.\n\n'
            '* Library: [`charmlibs.interfaces.foo`](project:#charmlibs-interfaces-foo)\n'
            '* Status: published\n\n'
            '## Behavior\n\n'
            f'[x]({base}/y.md)\n\n'
            '## Relation data\n\n'
            f'Generated from the [Pydantic schema]({base}/schema.py).\n'
        )
    )


# --- the header ---


def _version_dir(tmp_path: pathlib.Path, interface_yaml: str) -> pathlib.Path:
    version_dir = tmp_path / 'interfaces' / 'foo_bar' / 'interface' / 'v0'
    version_dir.mkdir(parents=True)
    (version_dir / 'interface.yaml').write_text(interface_yaml)
    return version_dir


def test_header_uses_the_name_from_the_metadata(tmp_path: pathlib.Path):
    version_dir = _version_dir(tmp_path, 'name: foo-bar\n')
    assert ip._render_header(version_dir, frozenset()) == '# `foo-bar/v0`'


def test_header_without_metadata_uses_the_directory_name(tmp_path: pathlib.Path):
    version_dir = tmp_path / 'interfaces' / 'foo_bar' / 'interface' / 'v0'
    version_dir.mkdir(parents=True)
    assert ip._render_header(version_dir, frozenset()) == '# `foo_bar/v0`'


def test_header_falls_back_to_the_summary(tmp_path: pathlib.Path):
    version_dir = _version_dir(tmp_path, 'summary: In short.\ndescription:\nlib: ""\n')
    assert ip._render_header(version_dir, frozenset()) == '# `foo_bar/v0`\n\nIn short.'


def test_header_ignores_fields_that_are_not_scalars(tmp_path: pathlib.Path):
    version_dir = _version_dir(tmp_path, 'status: []\nversion: 0\nproviders: []\n')
    assert ip._render_header(version_dir, frozenset()) == '# `foo_bar/v0`'


def test_header_with_malformed_metadata_warns(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    logger = ip._Logger()
    monkeypatch.setattr(ip, '_logger', logger)
    version_dir = _version_dir(tmp_path, '- foo\n')
    assert ip._render_header(version_dir, frozenset()) == '# `foo_bar/v0`'
    assert logger.count == 1


@pytest.mark.parametrize(
    ('lib', 'expected'),
    [
        (
            'charmlibs.interfaces.foo_bar',
            '[`charmlibs.interfaces.foo_bar`](project:#charmlibs-interfaces-foo-bar)',
        ),
        (
            'charmlibs.interfaces.other',
            '[`charmlibs.interfaces.other`](https://pypi.org/project/charmlibs-interfaces-other/)',
        ),
        (
            'dpcharmlibs.interfaces',
            '[`dpcharmlibs.interfaces`](https://pypi.org/project/dpcharmlibs-interfaces/)',
        ),
        ('cosl', '[`cosl`](https://pypi.org/project/cosl/)'),
        ('charms.foo.bar', '`charms.foo.bar` (Charmhub-hosted)'),
        ('charms.foo', '`charms.foo`'),
        ('not a library', '`not a library`'),
    ],
)
def test_render_lib(lib: str, expected: str):
    labels = frozenset({'charmlibs-interfaces-foo-bar'})
    assert ip._render_lib(lib, labels) == expected


def test_package_labels(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ip.subprocess, 'check_output', _fake_ls(['pathops', 'interfaces/tls-certificates'])
    )
    assert ip._package_labels() == {'charmlibs-pathops', 'charmlibs-interfaces-tls-certificates'}


# --- _without_title ---


@pytest.mark.parametrize(
    ('readme', 'expected'),
    [
        ('# foo\n\nText.\n', 'Text.'),
        ('\n# foo\n## Behavior\n', '## Behavior'),
        ('## Behavior\n\n# Later\n', '## Behavior\n\n# Later'),
        ('```\n# comment\n```\n', '```\n# comment\n```'),
        ('# foo\n# bar\n', '# bar'),
        ('No title.\n', 'No title.'),
    ],
)
def test_without_title(readme: str, expected: str):
    assert ip._without_title(readme) == expected


# --- _rewrite_links ---


def test_rewrite_links_relative():
    content = 'See [the schema](schema.md) for details.'
    result = ip._rewrite_links(content, 'https://example.com/base')
    assert result == 'See [the schema](https://example.com/base/schema.md) for details.'


def test_rewrite_links_preserves_http():
    content = 'See [docs](https://example.com/page) and [other](http://example.com/).'
    assert ip._rewrite_links(content, 'https://example.com/base') == content


def test_rewrite_links_multiple_relative_on_one_line():
    content = 'See [the schema](schema.py) and [the README](README.md).'
    result = ip._rewrite_links(content, 'https://example.com/base')
    assert result == (
        'See [the schema](https://example.com/base/schema.py)'
        ' and [the README](https://example.com/base/README.md).'
    )


def test_rewrite_links_mixed_on_one_line():
    content = 'See [docs](https://example.com/page), [schema](schema.py), [other](http://x/).'
    result = ip._rewrite_links(content, 'https://example.com/base')
    assert result == (
        'See [docs](https://example.com/page),'
        ' [schema](https://example.com/base/schema.py), [other](http://x/).'
    )


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
