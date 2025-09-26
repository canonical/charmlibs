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

"""Handle generation, saving, and restoration of package reference docs.

Packages are not guaranteed to have compatible dependencies, so we generate their reference docs
in separate invocations of ``sphinx-build``. If the ``package`` config option is set, we write
an ``audodoc`` ``automodule`` directive for that package, and then save the resulting doctree and
index information for that package. If the ``package`` config option is not set, we restore any
saved information when doctrees are resolved.
"""

from __future__ import annotations

import json
import pathlib
import pickle  # noqa: S403
import subprocess
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import docutils.nodes
    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _package_docs)
    app.connect('doctree-read', _load_on_doctree_read)
    app.connect('doctree-resolved', _save_on_doctree_resolved)
    app.add_config_value('package', default=None, rebuild='')
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _package_docs(app: sphinx.application.Sphinx) -> None:
    _main(docs_dir=pathlib.Path(app.confdir), package=app.config.package)


def _load_on_doctree_read(app: sphinx.application.Sphinx, doctree: docutils.nodes.document):
    """Load pickle file named after docname if it exists, and replace doctree contents in-place."""
    if app.config.package is not None:  # only load when not building docs for a specific package
        return
    if not (source := pathlib.Path('.save', app.env.docname)).exists():
        return
    saved, objects, modules = pickle.loads(source.read_bytes())  # noqa: S301
    # restore saved doctree
    doctree.clear()
    for node in saved.children:
        doctree.append(node)
    # restore domain inventory for cross-refs
    app.env.domains['py'].data['objects'].update(objects)
    app.env.domains['py'].data['modules'].update(modules)


def _save_on_doctree_resolved(
    app: sphinx.application.Sphinx, doctree: docutils.nodes.document, docname: str
):
    """Dump doctree to pickle file named after docname."""
    package = app.config.package
    # only save when building docs for a specific package
    # only save package reference docs
    if package is None or docname != f'reference/charmlibs/{package}':
        return
    objects = app.env.domains['py'].data['objects']
    modules = app.env.domains['py'].data['modules']
    target = pathlib.Path('.save', docname)
    target.parent.mkdir(exist_ok=True, parents=True)
    target.write_bytes(pickle.dumps((doctree, objects, modules)))


####################
# generation logic #
####################

RST_TEMPLATE = """
.. raw:: html

   <style>
      h1:before {{
         content: "{prefix}";
      }}
   </style>

{package}
{underline}
""".strip()
AUTOMODULE_TEMPLATE = """

.. automodule:: {package}
""".rstrip()


def _main(docs_dir: pathlib.Path, package: str | None) -> None:
    """Write automodule file for package and placeholders rst files for all other packages."""
    root = docs_dir.parent
    ref_dir = docs_dir / 'reference'
    (ref_dir / 'charmlibs' / 'interfaces').mkdir(parents=True, exist_ok=True)
    cmd = [root / '.scripts/ls.py', 'packages', '--exclude-examples', '--exclude-placeholders']
    packages = json.loads(subprocess.check_output(cmd, text=True))
    for raw_package in packages:
        subdir, _, p = raw_package.rpartition('/')
        module = p.replace('-', '_')
        content = RST_TEMPLATE.format(
            prefix=f'charmlibs.{subdir}.' if subdir else 'charmlibs.',
            package=module,
            underline='=' * len(module),
        )
        if package is not None and package == str(pathlib.Path(subdir, p)):
            content += AUTOMODULE_TEMPLATE.format(package=module)
        _write_if_needed(path=ref_dir / 'charmlibs' / subdir / f'{p}.rst', content=content)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
