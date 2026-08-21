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

"""Generate interface reference docs in the Sphinx source tree.

Walks every interface returned by ``.scripts/ls.py interfaces``, and for each
one writes an index stub with a glob toctree under ``reference/interfaces/``,
plus one page per ``interface/v[0-9]*/README.md`` with relative links
rewritten to absolute GitHub URLs.

Run from ``just docs``; see ``docs.just`` for the invocation.

This is a standalone preprocessor script rather than a Sphinx extension,
following the same pattern as ``diataxis_preprocessor.py``. Unlike the
package reference docs, interface docs don't use autodoc, so nothing here
needs to run inside a Sphinx build. Generating the pages once up front —
instead of in a ``builder-inited`` hook on every Sphinx pass — keeps the
per-package intermediate passes cheaper and the extension machinery simpler.
The companion ``interface_docs`` extension is now only a fallback: it writes
a placeholder page when this script hasn't run, so the glob toctree in
``reference/interfaces.md`` still matches at least one document.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess

_DOCS_DIR = pathlib.Path(__file__).parent.parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
_REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'

_INDEX_TEMPLATE = """
({label})=
# {interface_name}

```{{toctree}}
:glob:
:reversed:
:maxdepth: 1

{interface_name}/*
```
""".strip()


def _main() -> None:
    """Write an index stub and rewritten version READMEs for every interface."""
    ref_dir = _DOCS_DIR / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / 'placeholder.md').unlink(missing_ok=True)
    cmd = [
        _REPO_ROOT / '.scripts' / 'ls.py',
        'interfaces',
        '--exclude-examples',
        '--exclude-placeholders',
    ]
    interfaces: list[str] = json.loads(subprocess.check_output(cmd, text=True))
    for path_str in interfaces:
        _generate_interface_docs(interface_dir=_REPO_ROOT / path_str, ref_dir=ref_dir)


def _generate_interface_docs(interface_dir: pathlib.Path, ref_dir: pathlib.Path) -> None:
    """Write the index stub and rewritten version READMEs for one interface."""
    interface_name = interface_dir.name
    interface_ref_dir = ref_dir / interface_name
    interface_ref_dir.mkdir(exist_ok=True)
    label = f'interfaces-{interface_name.replace("_", "-")}'
    index = _INDEX_TEMPLATE.format(label=label, interface_name=interface_name)
    _write_if_needed(path=ref_dir / f'{interface_name}.md', content=index)
    for v in (interface_dir / 'interface').glob('v[0-9]*'):
        readme_raw = (v / 'README.md').read_text()
        base_url = f'{_REPO_MAIN_URL}/interfaces/{interface_name}/interface/{v.name}'
        readme = _rewrite_links(readme_raw, base_url)
        content = f'({label}-{v.name})=\n' + readme
        _write_if_needed(path=interface_ref_dir / f'{v.name}.md', content=content)


def _rewrite_links(content: str, base_url: str) -> str:
    """Rewrite relative markdown links to absolute GitHub URLs under ``base_url``."""
    return re.sub(
        # match all non-http(s) markdown links and prepend base_url to matching links
        r'\[(.+)\]\((?!https?://)([^)]+)\)',
        lambda m: f'[{m.group(1)}]({base_url}/{m.group(2)})',
        content,
    )


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this script
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


if __name__ == '__main__':
    _main()
