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

"""Sphinx fallback extension for interface reference docs.

The ``interface_preprocessor.py`` script (run by ``just docs``) generates the
interface reference pages under ``reference/interfaces/``.

This extension provides a fallback: if no interface reference pages exist —
because the preprocessor hasn't run — it writes a placeholder page so that the
glob toctree in ``reference/interfaces.md`` matches at least one document. If
the preprocessor has generated pages, it removes any stale placeholder instead.
"""

from __future__ import annotations

import pathlib
import typing

if typing.TYPE_CHECKING:
    import sphinx.application

_PLACEHOLDER_NAME = 'placeholder.md'


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Sphinx extension entrypoint — registers the fallback hook."""
    app.connect('builder-inited', _fallback)
    return {'version': '2.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _fallback(app: sphinx.application.Sphinx) -> None:
    ref_dir = pathlib.Path(app.confdir, 'reference', 'interfaces')
    ref_dir.mkdir(parents=True, exist_ok=True)
    placeholder = ref_dir / _PLACEHOLDER_NAME
    if any(p.name != _PLACEHOLDER_NAME for p in ref_dir.glob('*.md')):
        # The preprocessor has generated the interface reference pages.
        # Remove any stale placeholder so it isn't picked up by the glob toctree.
        placeholder.unlink(missing_ok=True)
    elif not placeholder.exists():
        placeholder.write_text('# Temporary TOC placeholder')
