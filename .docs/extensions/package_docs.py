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

import pathlib
import pickle  # noqa: S403
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import docutils.nodes
    import sphinx.application
    import sphinx.environment

SAVED_OBJECTS = pathlib.Path('.save', 'objects')
SAVED_DOCTREES = pathlib.Path('.save', 'doctrees')


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _package_docs)
    app.connect('env-before-read-docs', _load_domain_objects_on_env_before_read_docs)
    app.connect('doctree-read', _load_doctree_on_doctree_read)
    app.connect('doctree-resolved', _save_on_doctree_resolved)
    app.add_config_value('package', default=None, rebuild='')
    app.add_config_value('save_objects', default=False, rebuild='', types=[bool])
    app.add_config_value('save_doctrees', default=False, rebuild='', types=[bool])
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _package_docs(app: sphinx.application.Sphinx) -> None:
    _main(docs_dir=pathlib.Path(app.confdir), package=app.config.package)


def _load_domain_objects_on_env_before_read_docs(
    app: sphinx.application.Sphinx, env: sphinx.environment.BuildEnvironment, docnames: list[str]
) -> None:
    if app.config.save_objects:  # only load when not saving objects so we cleanly save separately
        return
    python_domain_data = env.domains['py'].data
    for path in SAVED_OBJECTS.rglob('*'):
        if path.is_dir():
            continue
        docname = str(path.relative_to(SAVED_OBJECTS))
        assert docname in env.found_docs, f'Unknown {docname=}, perhaps run `just docs clean`?'
        objects, modules = pickle.loads(path.read_bytes())  # noqa: S301
        python_domain_data['objects'].update(objects)
        python_domain_data['modules'].update(modules)
    if app.config.package is None:  # building docs for all packages, so ensure all links rebuild
        docnames[:] = sorted(env.found_docs)


def _load_doctree_on_doctree_read(
    app: sphinx.application.Sphinx, doctree: docutils.nodes.document
) -> None:
    """Load pickle file named after docname if it exists, and replace doctree contents in-place."""
    if app.config.package is not None:  # only load when not building docs for a specific package
        return
    if not (source := SAVED_DOCTREES / app.env.docname).exists():
        return
    saved = pickle.loads(source.read_bytes())  # noqa: S301
    # restore saved doctree
    doctree.clear()
    for node in saved.children:
        doctree.append(node)


def _save_on_doctree_resolved(
    app: sphinx.application.Sphinx, doctree: docutils.nodes.document, docname: str
):
    """Dump doctree to pickle file named after docname."""
    package = app.config.package
    # only save when building docs for a specific package
    # only save package reference docs
    if package is None or docname != f'reference/charmlibs/{package}':
        return
    if app.config.save_objects:
        objects = app.env.domains['py'].data['objects']
        modules = app.env.domains['py'].data['modules']
        target = SAVED_OBJECTS / docname
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(pickle.dumps((objects, modules)))
    if app.config.save_doctrees:
        target = SAVED_DOCTREES / docname
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(pickle.dumps(doctree))


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
    # Any directory (or subdirectory of interfaces/) starting with a-z is assumed to be a package.
    for subdir, p in (
        *(('', p.name) for p in root.glob(r'[a-z]*') if p.is_dir() and p.name != 'interfaces'),
        *(('interfaces', p.name) for p in (root / 'interfaces').glob(r'[a-z]*') if p.is_dir()),
    ):
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
