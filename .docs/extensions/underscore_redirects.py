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
    app.connect('env-updated', _populate)
    return {
        'version': '1.0.0',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }


def _populate(app: sphinx.application.Sphinx, env: sphinx.environment.BuildEnvironment) -> None:
    # Skip the per-package reference passes: they only build a subset of pages,
    # so most redirect targets would be missing. The final combined pass
    # (where 'package' is unset) is the one that writes the full site.
    if getattr(app.config, 'package', None) is not None:
        return
    # Only extend an existing dict mapping. If a user has configured
    # rediraffe_redirects as a filename (str) or left it unset, respect that
    # and don't clobber it.
    existing = app.config.rediraffe_redirects
    if not isinstance(existing, dict):
        return
    for variant, target in _build_redirects(set(env.found_docs)).items():
        # Never overwrite a user-configured redirect.
        if variant not in existing:
            existing[variant] = target


def _build_redirects(found_docs: set[str]) -> dict[str, str]:
    """Return a ``{variant: original}`` redirect mapping for the given docnames.

    For each docname, the separator-swapped variant (``-`` <-> ``_`` in every
    path segment) is computed. If the variant differs from the original and is
    not itself a real page, a redirect is added from the variant to the
    original. Existing user redirects are never overwritten.
    """
    redirects: dict[str, str] = {}
    for docname in found_docs:
        variant = _separator_variant(docname)
        if variant is None:
            continue
        if variant in found_docs:
            # Both separator variants are real pages; don't shadow either.
            continue
        if variant in redirects:
            # Two originals map to the same variant (shouldn't happen with a
            # pure swap, but guard against it regardless).
            continue
        redirects[variant] = docname
    return redirects


def _separator_variant(docname: str) -> str | None:
    """Return the docname with ``-`` and ``_`` swapped in each segment.

    Returns ``None`` when the result is identical to the input (that is, when
    no path segment contains either separator). Uses a NUL placeholder so the
    swap is a true involution even for segments containing both separators.
    """
    new_parts: list[str] = []
    changed = False
    for part in docname.split('/'):
        new_part = part.replace('-', '\0').replace('_', '-').replace('\0', '_')
        if new_part != part:
            changed = True
        new_parts.append(new_part)
    if not changed:
        return None
    return '/'.join(new_parts)
