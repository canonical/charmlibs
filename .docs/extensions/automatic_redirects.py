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

"""Populate ``rediraffe_redirects`` with underscore/hyphen separator variants.

All hand-written docs pages use hyphens in their slugs (for example
``how-to/manage-libraries``). This extension makes the underscore versions
(``how_to/manage_libraries``) resolve too, by generating redirects from the
separator-swapped variant of every page to the page itself.

The mapping is populated into the ``rediraffe_redirects`` config value, which
is consumed by the ``sphinx-rerediraffe`` extension (enabled in ``conf.py``)
to write the actual redirect HTML during the build. rediraffe also validates
that every redirect target exists, so a misconfigured redirect fails the
build rather than silently 404ing.

The mapping is symmetric: for each existing page, the variant with ``-`` and
``_`` swapped in every path segment is computed. If that variant is not
already a real page, a redirect is added from the variant to the page. This
means hyphenated pages get underscore aliases *and* underscored pages (for
example, interface reference pages like
``reference/interfaces/fiveg_core_gnb/v1``) get hyphen aliases. When both
separators are already real pages, no redirect is generated for either.

Only the final combined docs pass populates the mapping. Per-package
reference passes (where ``package`` is set) are skipped, because those passes
only build a subset of pages and most redirect targets would not exist.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import sphinx.application
    import sphinx.environment


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Sphinx extension entrypoint -- register the ``env-updated`` hook."""
    app.connect('env-updated', _automatic_redirects)
    return {'version': '1.0.0', 'parallel_read_safe': True, 'parallel_write_safe': True}


def _automatic_redirects(
    app: sphinx.application.Sphinx, env: sphinx.environment.BuildEnvironment
) -> None:
    # Don't create redirects during the per-package passes.
    if app.config.package is not None:
        return
    target = typing.cast('dict[str, str]', app.config.rediraffe_redirects)
    assert isinstance(target, dict)
    redirects = _build_redirects(set(env.found_docs))
    assert set(target).isdisjoint(redirects)
    target.update(redirects)


def _build_redirects(found_docs: set[str]) -> dict[str, str]:
    """Redirect underscored names to hyphenated ones and vice versa.

    Categories area also separately aliased with both variants and with no separator.
    """
    redirects: dict[str, str] = {}
    for docname in sorted(found_docs):
        category, _, doc = docname.partition('/')
        category_variants = {
            category,
            category.replace('-', '_'),  # e.g. how_to
            category.replace('_', '-'),  # e.g. how-to
            category.replace('_', '').replace('-', ''),  # e.g. howto
        }
        for category_variant in sorted(category_variants):
            doc_variant = _separator_variant(doc)
            if (category_variant, doc_variant) == (category, doc):
                continue
            alias = f'{category_variant}/{doc_variant}'
            assert alias not in found_docs, f'Alias {alias} is a real page!'
            assert alias not in redirects, f'Alias {alias} already redirects to {redirects[alias]}'
            redirects[alias] = docname.removesuffix('index.html')
    return redirects


def _separator_variant(docname: str) -> str:
    """Return the docname with ``-`` and ``_`` swapped."""
    if '-' in docname:
        assert '_' not in docname, f"Docname {docname} should not contain both '-' and '_'"
        return docname.replace('-', '_')
    if '_' in docname:
        assert '-' not in docname, f"Docname {docname} should not contain both '-' and '_'"
        return docname.replace('_', '-')
    return docname
