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

"""Write placeholder rst files for every package's reference docs.

Packages are not guaranteed to have compatible dependencies, so we generate their reference docs
in separate invocations of ``sphinx-build``. Each of those builds needs a page to hang its
``automodule`` output on, and this script writes those pages.

This is a standalone preprocessor script rather than part of the companion ``package_docs``
extension. The placeholders are identical no matter which package is being built, so writing
them is a one-time preparation of the source tree rather than per-build work. Doing it once, up
front, is also what makes it safe to run the per-package builds concurrently: they share the
same source tree but never mutate each other's rst files. The ``package_docs`` extension appends
the ``automodule`` directive for the current package in memory at ``source-read`` time, so the
on-disk files stay plain placeholders.

Library packages and their testing packages (see ``package_docs`` for details) both get a
placeholder page here, cross-linked with a ``seealso`` back to each other. Where a page lives,
and how it's titled and labelled, is decided by ``package_docs._page()`` -- imported from here
rather than reimplemented, so that this script and the ``package_docs`` extension can't drift.

Run from ``just docs``; see ``docs.just`` for the invocation.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import typing

_DOCS_DIR = pathlib.Path(__file__).parent.parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
sys.path.insert(0, str(_DOCS_DIR / 'extensions'))
import package_docs  # noqa: E402

RST_TEMPLATE = """
.. raw:: html

   <style>
      h1:before {{
         content: "{import_prefix}";
      }}
   </style>

.. _{label}:

{import_name}
{underline}
""".strip()


TESTING_TOCTREE_TEMPLATE = """
```{{toctree}}
:maxdepth: 1

{entries}
```
""".strip()


def _main() -> None:
    """Write placeholder rst files for every package, including testing packages."""
    ls = _REPO_ROOT / '.scripts' / 'ls.py'
    cmd = [ls, 'packages', '--exclude-examples', '--exclude-placeholders']
    raw_packages: list[str] = json.loads(subprocess.check_output(cmd, text=True))
    pages = {raw_package: package_docs._page(raw_package) for raw_package in raw_packages}
    _write_testing_toctree(pages.values())
    for raw_package, page in pages.items():
        content = RST_TEMPLATE.format(
            import_prefix=page.import_prefix,
            import_name=page.import_name,
            underline='=' * len(page.import_name),
            label=page.label,
        )
        related = package_docs._related_page(raw_package, pages)
        if related is not None:
            text = 'Library reference:' if page.is_testing else 'Testing helpers:'
            content += package_docs.SEEALSO_TEMPLATE.format(
                text=text, import_path=related.import_path, label=related.label
            )
        path = _DOCS_DIR / f'{page.docname}.rst'
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_if_needed(path=path, content=content)


def _write_testing_toctree(pages: typing.Iterable[package_docs._Page]) -> None:
    """Write the toctree that ``reference/testing.md`` includes.

    A generated include rather than a ``:glob:`` in the page itself, because a glob that
    matches nothing is a warning, and the docs build treats warnings as errors. Testing
    packages are optional and there may be none at all -- in a repository that has none yet,
    or on a branch where the only one has been split out -- and that has to build cleanly.
    Mirrors what ``extensions/diataxis_docs_fallback.py`` does for the per-library docs.
    """
    entries = sorted(page.docname.removeprefix('reference/') for page in pages if page.is_testing)
    content = TESTING_TOCTREE_TEMPLATE.format(entries='\n'.join(entries)) if entries else ''
    _write_if_needed(path=_DOCS_DIR / 'reference' / '_testing-packages.md', content=content)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on this script's output if the
    output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


if __name__ == '__main__':
    _main()
