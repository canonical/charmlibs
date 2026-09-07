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

Run from ``just docs``; see ``docs.just`` for the invocation.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess

_DOCS_DIR = pathlib.Path(__file__).parent.parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
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


def _main() -> None:
    """Write placeholder rst files for every package."""
    ref_dir = _DOCS_DIR / 'reference'
    (ref_dir / 'charmlibs' / 'interfaces').mkdir(parents=True, exist_ok=True)
    ls = _REPO_ROOT / '.scripts' / 'ls.py'
    cmd = [ls, 'packages', '--exclude-examples', '--exclude-placeholders', '--exclude-testing']
    packages = json.loads(subprocess.check_output(cmd, text=True))
    for raw_package in packages:
        subdir, _, p = raw_package.rpartition('/')
        canonical_path = ['charmlibs']
        if subdir:
            canonical_path.append(_normalize(subdir))
        canonical_path.append(_normalize(p))
        *import_prefix_parts, import_name = (part.replace('-', '_') for part in canonical_path)
        content = RST_TEMPLATE.format(
            import_prefix='.'.join(import_prefix_parts) + '.',
            import_name=import_name,
            underline='=' * len(p),
            label='-'.join(canonical_path),
        )
        path = ref_dir.joinpath(*canonical_path).with_suffix('.rst')
        _write_if_needed(path=path, content=content)


def _normalize(name: str) -> str:
    """Normalize distribution package name according to PyPI rules.

    https://packaging.python.org/en/latest/specifications/name-normalization/#name-normalization
    """
    return re.sub(r'[-_.]+', '-', name).lower()


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on this script's output if the
    output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


if __name__ == '__main__':
    _main()
