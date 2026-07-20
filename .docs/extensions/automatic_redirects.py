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

import sphinx.application
import sphinx.environment
import sphinx.util.logging

if typing.TYPE_CHECKING:
    from collections.abc import Generator


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

    Categories are also separately aliased with both variants and with no separator.
    """
    redirects: dict[str, str] = {}
    for docname in sorted(found_docs):
        for alias in sorted(set(_variants(docname))):
            if alias == docname:
                continue
            assert alias not in found_docs, f'Alias {alias} is a real page!'
            assert alias not in redirects, f'Alias {alias} already redirects to {redirects[alias]}'
            # We assume we always run *before* any /index.html shenanigans.
            assert not docname.endswith('/index.html'), f'Unexpected docname format: {docname}'
            redirects[alias] = docname
    return redirects


def _variants(docname: str) -> Generator[str]:
    """Return underscored and hyphenated variants of docname.

    The category is also varied in non-separated form.
    """
    # Example input: how-to/some_interface/foo-bar
    yield docname.replace('-', '_')  # -> how_to/some_interface/foo_bar
    yield docname.replace('_', '-')  # -> how-to/some-interface/foo-bar
    category, sep, doc = docname.partition('/')
    cat = category.replace('_', '').replace('-', '')
    yield cat + sep + doc.replace('-', '_')  # -> howto/some_interface/foo_bar
    yield cat + sep + doc.replace('_', '-')  # -> howto/some-interface/foo-bar
