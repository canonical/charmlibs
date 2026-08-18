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
in separate invocations of ``sphinx-build``. If the ``package`` config option is set, we inject
an ``audodoc`` ``automodule`` directive for that package at source-read time, and then save the
resulting doctree and index information for that package. If the ``package`` config option is not
set, we restore any saved information when doctrees are resolved.

The on-disk rst files are always plain placeholders — the automodule directive is only added
in-memory during ``source-read`` for the current package. This is what makes it safe to run
per-package sphinx-build invocations concurrently: they share the same source tree but never
mutate each other's rst files.
"""

from __future__ import annotations

import json
import pathlib
import pickle  # noqa: S403
import re
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
    app.connect('source-read', _append_automodule_on_source_read)
    app.connect('doctree-read', _load_on_doctree_read)
    app.connect('doctree-resolved', _save_on_doctree_resolved)
    app.add_config_value('package', default=None, rebuild='')
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _package_docs(app: sphinx.application.Sphinx) -> None:
    _main(docs_dir=pathlib.Path(app.confdir))


def _append_automodule_on_source_read(
    app: sphinx.application.Sphinx, docname: str, source: list[str]
) -> None:
    """Inject the automodule directive for the current per-package build.

    Runs during Sphinx's ``source-read`` event, after the placeholder rst file has been loaded
    and before it's parsed. In-memory mutation only — the on-disk file stays a placeholder, so
    concurrent per-package builds don't step on each other.
    """
    package = app.config.package
    if package is None:
        return
    subdir, _, p = package.rpartition('/')
    canonical_path = ['charmlibs']
    if subdir:
        canonical_path.append(_normalize(subdir))
    canonical_path.append(_normalize(p))
    if docname != '/'.join(('reference', *canonical_path)):
        return
    import_name = canonical_path[-1].replace('-', '_')
    source[0] = source[0] + AUTOMODULE_TEMPLATE.format(package=import_name)


def _load_on_doctree_read(app: sphinx.application.Sphinx, doctree: docutils.nodes.document):
    """Load pickle file named after docname if it exists, and replace doctree contents in-place."""
    if app.config.package is not None:  # only load when not building docs for a specific package
        return
    if not (source := pathlib.Path('.save', f'{app.env.docname}.pickle')).exists():
        return
    saved, objects, modules, toc, toc_num_entries = pickle.loads(source.read_bytes())  # noqa: S301
    # restore saved doctree
    doctree.clear()
    for node in saved.children:
        doctree.append(node)
    # restore domain inventory for cross-refs
    app.env.domains['py'].data['objects'].update(objects)
    app.env.domains['py'].data['modules'].update(modules)
    # restore TOC so the RHS table of contents is populated
    docname = app.env.docname
    app.env.tocs[docname] = toc
    app.env.toc_num_entries[docname] = toc_num_entries


def _save_on_doctree_resolved(
    app: sphinx.application.Sphinx, doctree: docutils.nodes.document, docname: str
):
    """Dump doctree to pickle file named after docname."""
    package = app.config.package
    # only save when building docs for a specific package
    # only save package reference docs
    if package is None or docname != f'reference/charmlibs/{_normalize(package)}':
        return
    objects = app.env.domains['py'].data['objects']
    modules = app.env.domains['py'].data['modules']
    toc = app.env.tocs[docname]
    toc_num_entries = app.env.toc_num_entries[docname]
    target = pathlib.Path('.save', f'{docname}.pickle')
    target.parent.mkdir(exist_ok=True, parents=True)
    target.write_bytes(pickle.dumps((doctree, objects, modules, toc, toc_num_entries)))


####################
# generation logic #
####################

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
AUTOMODULE_TEMPLATE = """

.. automodule:: {package}
""".rstrip()


def _main(docs_dir: pathlib.Path) -> None:
    """Write placeholder rst files for every package.

    The automodule directive is appended in-memory at ``source-read`` time for the current
    per-package build; on-disk files are always the same plain placeholder regardless of which
    build wrote them, so concurrent per-package builds share the source tree safely.
    """
    root = docs_dir.parent
    ref_dir = docs_dir / 'reference'
    (ref_dir / 'charmlibs' / 'interfaces').mkdir(parents=True, exist_ok=True)
    ls = root / '.scripts' / 'ls.py'
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

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
