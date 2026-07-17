#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# ///

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

"""Copy per-library diataxis docs into the Sphinx source tree.

Walks every package returned by ``.scripts/ls.py``, looks for a ``docs/``
directory, and copies tutorial, how-to, and explanation pages into the
corresponding Sphinx source directories. Generates ``_lib-*.md`` include
files containing toctree entries that the index pages pull in via
``{include}``.

Run from ``just docs``; see ``docs.just`` for the invocation.

This is a standalone preprocessor script rather than a Sphinx extension. A
preprocessor step is simpler and more maintainable than an extension in
general, and it's a particularly good fit here: we want this work to run only
once (an extension would need extra machinery to enable/disable itself per
build, like the package reference docs do), and we need it to run very early
— before Sphinx has started building a docs tree of any kind. Copying the
source files and rewriting links is a one-time preparation of the source tree
that a final, straightforward Sphinx build then consumes. The companion
``diataxis_docs_fallback`` extension only writes empty ``_lib-*.md``
placeholders when this script hasn't written anything, so the ``{include}``
directives still resolve.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Any

_DOCS_DIR = pathlib.Path(__file__).parent.parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
_REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'
_TOCTREE_HEADER = """\
```{toctree}
:maxdepth: 1

"""
_TOCTREE_FOOTER = '```\n'


def _main() -> None:
    """Discover packages and copy their docs into the Sphinx source tree."""
    cmd = [
        _REPO_ROOT / '.scripts' / 'ls.py',
        'packages',
        '--exclude-examples',
        '--exclude-placeholders',
        '--exclude-testing',
        *('--output', 'path'),
        *('--output', 'docs'),
    ]
    packages: list[dict[str, Any]] = json.loads(subprocess.check_output(cmd, text=True))
    sphinx_map = _build_sphinx_map(packages)
    # Copy each package's docs and collect toctree entries for each category.
    all_entries: dict[str, list[str]] = {}
    for pkg in packages:
        lib_path = pathlib.PurePath(pkg['path'])
        docs: dict[str, list[str]] = pkg.get('docs', {})
        for category, doc_files in docs.items():
            sources = [_REPO_ROOT / lib_path / f for f in doc_files]
            entries = _copy_category(sources, lib_path, category, sphinx_map)
            all_entries.setdefault(category, []).extend(entries)
    # Write include files with toctree entries for each category.
    for category, entries in all_entries.items():
        if not entries:
            continue
        path = _DOCS_DIR / category / f'_lib-{category}.md'
        content = _TOCTREE_HEADER + '\n'.join(sorted(entries)) + '\n' + _TOCTREE_FOOTER
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _copy_category(
    sources: list[pathlib.Path],
    lib_path: pathlib.PurePath,
    category: str,
    sphinx_map: dict[pathlib.PurePath, str],
) -> list[str]:
    """Copy a library's docs for one category and return toctree entries."""
    if not sources:
        return []
    out_dir = _DOCS_DIR / category / 'charmlibs' / lib_path
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    for source in sources:
        content = source.read_text()
        title = _extract_h1(content, source)
        content = _prefix_h1(content, lib_path.name, source.suffix)
        content = _rewrite_links(content, source, sphinx_map)
        (out_dir / source.name).write_text(content)
        entries.append(f'{lib_path.name}: {title} <charmlibs/{lib_path}/{source.stem}>')
    return entries


def _extract_h1(content: str, source: pathlib.Path) -> str:
    """Extract the first H1 heading text from content."""
    if source.suffix == '.md':
        match = re.search(r'^# (.+)$', content, re.MULTILINE)
    else:
        match = re.search(r'^(.+)\n(?:=+|-+)$', content, re.MULTILINE)
    if not match:
        raise ValueError(f'no title found in {source}')
    return match.group(1).strip()


def _prefix_h1(content: str, lib_name: str, ext: str) -> str:
    """Prepend the library name to the first H1 heading."""
    if ext == '.md':
        return re.sub(r'^(# )', rf'\1{lib_name}: ', content, count=1, flags=re.MULTILINE)

    def _replace(m: re.Match[str]) -> str:
        title = f'{lib_name}: {m.group(1)}'
        return f'{title}\n{m.group(2)[0] * len(title)}'

    return re.sub(r'^(.+)\n(=+|-+)$', _replace, content, count=1, flags=re.MULTILINE)


def _build_sphinx_map(packages: list[dict[str, Any]]) -> dict[pathlib.PurePath, str]:
    """Build a mapping from repo-relative file paths to Sphinx doc paths.

    Covers:
    - ``.docs/`` pages (how-to, explanation, tutorials, reference, etc.)
    - Per-library diataxis docs (tutorial, how-to/*, explanation/*)
    - Interface version READMEs (``interfaces/{name}/interface/v{N}/README.md``)
    """
    docs_rel = _DOCS_DIR.relative_to(_REPO_ROOT)
    m: dict[pathlib.PurePath, str] = {}

    # Static .docs/ pages — walk all .md/.rst files (excluding build artifacts).
    skip_dirs = {'_build', '_dev', '.save', 'scripts', 'tests', 'extensions'}
    for path in _DOCS_DIR.rglob('*'):
        if path.suffix not in ('.md', '.rst'):
            continue
        rel = path.relative_to(_DOCS_DIR)
        if rel.parts[0] in skip_dirs or rel.name.startswith('_'):
            continue
        m[docs_rel / rel] = f'/{rel.with_suffix("")}'

    # Per-library diataxis docs + interface version READMEs.
    for pkg in packages:
        lib_path = pathlib.PurePath(pkg['path'])
        docs: dict[str, list[str]] = pkg.get('docs', {})
        for category, doc_files in docs.items():
            for doc_rel in doc_files:
                stem = pathlib.PurePath(doc_rel).stem
                m[lib_path / doc_rel] = f'/{category}/charmlibs/{lib_path}/{stem}'
        # Interface version READMEs (interfaces/{name}/interface/v{N}/README.md).
        if lib_path.parent.name == 'interfaces':
            interface_dir = _REPO_ROOT / lib_path / 'interface'
            for readme in interface_dir.glob('v[0-9]*/README.md'):
                m[readme.relative_to(_REPO_ROOT)] = (
                    f'/reference/interfaces/{lib_path.name}/{readme.parent.name}'
                )

    return m


def _rewrite_links(
    content: str, source_file: pathlib.Path, sphinx_map: dict[pathlib.PurePath, str]
) -> str:
    """Rewrite markdown links: Sphinx paths for known docs, GitHub URLs otherwise."""

    def _replace(m: re.Match[str]) -> str:
        text = m.group(1)
        raw_target = m.group(2)
        # Split off any anchor fragment.
        path_part, sep, raw_fragment = raw_target.partition('#')
        fragment = sep + raw_fragment  # either '' or '#something'
        # Resolve relative to the source file's directory.
        resolved = (source_file.parent / path_part).resolve()
        repo_rel = resolved.relative_to(_REPO_ROOT)  # ValueError if link goes above repo root
        # Look up in the Sphinx map, falling back to GitHub URL.
        url = sphinx_map.get(repo_rel, f'{_REPO_MAIN_URL}/{repo_rel}')
        return f'[{text}]({url}{fragment})'

    relative_link = (
        r'\[(.+?)\]'  # [link text] -- capture group 1
        r'\('  # (
        r'(?!https?://)'  # not an absolute URL
        r'([^)]+)'  # relative target -- capture group 2
        r'\)'  # )
    )
    return re.sub(relative_link, _replace, content)


if __name__ == '__main__':
    _main()
