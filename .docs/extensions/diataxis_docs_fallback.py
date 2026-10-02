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

"""Sphinx fallback extension for per-library diataxis docs.

The ``diataxis_preprocessor.py`` script (run by ``just docs``) copies library
docs into the Sphinx source tree and generates ``_lib-*.md`` include files.

This extension provides a fallback: if any of those include files don't exist
— either because the preprocessor wasn't run, or because no libraries have docs
for a given category — it writes empty versions so that the ``{include}``
directives in the category index pages resolve without errors.
"""

from __future__ import annotations

import pathlib
import typing

if typing.TYPE_CHECKING:
    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Sphinx extension entrypoint — registers the fallback hook."""
    app.connect('builder-inited', _fallback)
    return {'version': '2.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _fallback(app: sphinx.application.Sphinx) -> None:
    docs_dir = pathlib.Path(app.confdir)
    for category in 'tutorials', 'how-to', 'explanation':
        path = docs_dir / category / f'_lib-{category}.md'
        if not path.exists():
            path.write_text('')
