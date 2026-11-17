# Copyright 2026 Canonical Ltd.
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

# ruff: noqa: D103 (function docstrings)

"""Unit tests for the `package_docs` local Sphinx extension."""

from __future__ import annotations

import pathlib
import pickle  # noqa: S403
import types
import typing

import docutils.nodes
import docutils.utils
import package_docs
import pytest

if typing.TYPE_CHECKING:
    import sphinx.application

_DOCNAME = 'reference/charmlibs/snap'


def _app(docname: str, package: str | None = None) -> tuple[sphinx.application.Sphinx, list[str]]:
    """Return a stand-in for the Sphinx app, and the list its noted dependencies are added to."""
    dependencies: list[str] = []
    env = types.SimpleNamespace(
        docname=docname,
        domains={'py': types.SimpleNamespace(data={'objects': {}, 'modules': {}})},
        tocs={},
        toc_num_entries={},
        note_dependency=dependencies.append,
    )
    app = types.SimpleNamespace(config=types.SimpleNamespace(package=package), env=env)
    return typing.cast('sphinx.application.Sphinx', app), dependencies


def _doctree(text: str) -> docutils.nodes.document:
    doctree = docutils.utils.new_document('test')
    doctree.append(docutils.nodes.paragraph(text=text))
    return doctree


def _save(docname: str, text: str) -> pathlib.Path:
    """Write a pickle as the per-package build does, relative to the current directory."""
    toc = docutils.nodes.bullet_list()
    data = (_doctree(text), {'snap.install': 'object'}, {'snap': 'module'}, toc, 3)
    target = pathlib.Path('.save', f'{docname}.pickle')
    target.parent.mkdir(parents=True)
    target.write_bytes(pickle.dumps(data))
    return target


@pytest.fixture(autouse=True)
def _in_tmp_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The extension reads and writes .save/ relative to the current directory.
    monkeypatch.chdir(tmp_path)


class TestLoadOnDoctreeRead:
    def test_restores_saved_package_docs(self):
        _save(_DOCNAME, 'saved')
        app, _ = _app(_DOCNAME)
        doctree = _doctree('placeholder')
        package_docs._load_on_doctree_read(app, doctree)
        assert doctree.astext() == 'saved'
        assert app.env.domains['py'].data['objects'] == {'snap.install': 'object'}
        assert app.env.domains['py'].data['modules'] == {'snap': 'module'}
        assert _DOCNAME in app.env.tocs
        assert app.env.toc_num_entries[_DOCNAME] == 3

    def test_package_page_depends_on_its_pickle(self):
        # The placeholder rst never changes, so without the dependency an incremental build
        # would never re-read the page after the package's docs were rebuilt.
        target = _save(_DOCNAME, 'saved')
        app, dependencies = _app(_DOCNAME)
        package_docs._load_on_doctree_read(app, _doctree('placeholder'))
        assert dependencies == [str(target)]

    def test_package_page_depends_on_a_pickle_that_does_not_exist_yet(self):
        # Sphinx re-reads a page whose dependency is missing, so the page picks up its
        # package's docs once they have been built.
        app, dependencies = _app(_DOCNAME)
        doctree = _doctree('placeholder')
        package_docs._load_on_doctree_read(app, doctree)
        assert dependencies == [str(pathlib.Path('.save', f'{_DOCNAME}.pickle'))]
        assert doctree.astext() == 'placeholder'

    def test_interface_package_page_depends_on_its_pickle(self):
        docname = 'reference/charmlibs/interfaces/tls-certificates'
        app, dependencies = _app(docname)
        package_docs._load_on_doctree_read(app, _doctree('placeholder'))
        assert dependencies == [str(pathlib.Path('.save', f'{docname}.pickle'))]

    @pytest.mark.parametrize(
        'docname',
        [
            'index',
            'reference/index',
            'reference/charmlibs',
            'reference/charmlibs-interfaces',
            'how-to/charmlibs/snap/x',
        ],
    )
    def test_other_pages_get_no_dependency(self, docname: str):
        # A missing dependency makes Sphinx re-read a page on every build, so only the
        # package placeholder pages may be given one.
        app, dependencies = _app(docname)
        doctree = _doctree('unchanged')
        package_docs._load_on_doctree_read(app, doctree)
        assert dependencies == []
        assert doctree.astext() == 'unchanged'

    def test_does_nothing_in_a_package_build(self):
        _save(_DOCNAME, 'saved')
        app, dependencies = _app(_DOCNAME, package='snap')
        doctree = _doctree('placeholder')
        package_docs._load_on_doctree_read(app, doctree)
        assert dependencies == []
        assert doctree.astext() == 'placeholder'
