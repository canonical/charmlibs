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

"""Populate ``rediraffe_redirects`` with underscore/hyphen separator variants."""

from __future__ import annotations

import typing

import sphinx.util.logging

if typing.TYPE_CHECKING:
    import sphinx.application
    import sphinx.environment

logger = sphinx.util.logging.getLogger(__name__)


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
    redirects = _build_redirects(set(env.found_docs))
    logger.info('Generated automatic redirects.')  # Show with `-v`.
    for k, v in redirects.items():
        logger.verbose(f'- {k} -> {v}')  # Show with `-vv`.
    target = typing.cast('dict[str, str]', app.config.rediraffe_redirects)
    assert isinstance(target, dict), f'rediraffe_redirects must be a dict, not {target!r}'
    if not set(target.keys()).isdisjoint(redirects.keys()):
        lines = ['Manually configured redirects would be clobbered by automatic redirects:']
        lines.extend(
            f'{k} -> {target[k]} would be overwritten by {k} -> {v}'
            for k, v in redirects.items()
            if k in target
        )
        raise ValueError('\n - '.join(lines))
    if not set(target.values()).isdisjoint(redirects.keys()):
        lines = [
            'The following manually configured redirects would chain with automatic redirects:'
        ]
        lines.extend(
            f'{k} -> {v} should point to {redirects[v]}'
            for k, v in target.items()
            if v in redirects
        )
        raise ValueError('\n - '.join(lines))
    if not set(target.keys()).isdisjoint(redirects.values()):
        # This is probably safe in practice, but we'd like to notice the first time it happens.
        lines = ['The following automatic redirects chain with manually configured redirects:']
        lines.extend(f'{k} -> {v} -> {target[v]}' for k, v in redirects.items() if v in target)
        raise ValueError('\n - '.join(lines))
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
            category.replace('-', '_'),  # how_to
            category.replace('_', '-'),  # how-to
            category.replace('_', '').replace('-', ''),  # howto
        }
        for category_variant in sorted(category_variants):
            for doc_variant in sorted({doc, _separator_variant(doc)}):
                if (category_variant, doc_variant) == (category, doc):
                    continue
                alias = f'{category_variant}/{doc_variant}'
                assert alias not in found_docs, f'Alias {alias} is a real page!'
                assert alias not in redirects, (
                    f'Alias {alias} already redirects to {redirects[alias]}'
                )
                if docname.endswith('/index.html'):
                    # Remove 'index.html', preserve trailing '/'.
                    redirects[alias] = docname.removesuffix('index.html')
                else:
                    redirects[alias] = docname
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
