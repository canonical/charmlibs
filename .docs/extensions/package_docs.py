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

"""Generate automodule files and table of contents for packages."""

from __future__ import annotations

import pathlib
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _package_docs)
    app.add_config_value('package', default=None, rebuild='')
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _package_docs(app: sphinx.application.Sphinx) -> None:
    package = app.config.package
    if package is not None:
        _main(docs_dir=pathlib.Path(app.confdir), package=package)


####################
# generation logic #
####################

AUTOMODULE_TEMPLATE = """
.. raw:: html

   <style>
      h1:before {{
         content: "{prefix}";
      }}
   </style>

{package}
{underline}

.. automodule:: {package}
""".strip()


def _main(docs_dir: pathlib.Path, package: str) -> None:
    subdir, _, package_dir_name = package.rpartition('/')
    subdir = subdir or '.'
    generated_dir = docs_dir / 'reference' / 'charmlibs' / subdir
    generated_dir.mkdir(parents=True, exist_ok=True)
    root = docs_dir.parent
    assert (root / subdir / package_dir_name).is_dir()
    prefix = 'charmlibs.' if subdir == '.' else f'charmlibs.{subdir}.'
    module = package_dir_name.replace('-', '_')
    content = AUTOMODULE_TEMPLATE.format(
        prefix=prefix, package=module, underline='=' * len(package)
    )
    _write_if_needed(path=generated_dir / f'{package}.rst', content=content)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
