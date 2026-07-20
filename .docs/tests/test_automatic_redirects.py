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

"""Unit tests for the `automatic_redirects` local Sphinx extension."""

from __future__ import annotations

import types
import typing

import automatic_redirects
import pytest

if typing.TYPE_CHECKING:
    import sphinx.application


class TestSeparatorVariant:
    @pytest.mark.parametrize(
        ('docname', 'expected'),
        [
            # Hyphens are translated to underscores and vice versa.
            ('---', '___'),
            ('___', '---'),
            # / isn't special for this function.
            ('how-to/manage-libraries', 'how_to/manage_libraries'),
            ('how_to/manage_libraries', 'how-to/manage-libraries'),
            # If there are no separators, the value is returned unmodified.
            ('noseparators', 'noseparators'),
            ('', ''),
        ],
    )
    def test_ok(self, docname: str, expected: str):
        variant = automatic_redirects._separator_variant(docname)
        assert variant == expected

    def test_mixed_separators_raises(self):
        """A docname containing both separators is an error."""
        with pytest.raises(AssertionError, match='should not contain both'):
            automatic_redirects._separator_variant('-_-')


class TestBuildRedirects:
    @pytest.mark.parametrize(
        ('found', 'expected'),
        [
            # No separators -> no redirects.
            ({'foo', 'bar'}, {}),
            # Hyphen -> underscore and vice versa.
            ({'foo/a-b'}, {'foo/a_b': 'foo/a-b'}),
            ({'foo/a_b'}, {'foo/a-b': 'foo/a_b'}),
            # Redirects are created for category variants.
            ({'how-to/foo'}, {'how_to/foo': 'how-to/foo', 'howto/foo': 'how-to/foo'}),
            # Trailing /index.html is handled.
            ({'foo/a-b/index.html'}, {'foo/a_b/index.html': 'foo/a-b/'}),
            # Redirects are created from original name with category variant.
            (
                {'how-to/a-b/index.html'},
                {
                    'how-to/a_b/index.html': 'how-to/a-b/',
                    'how_to/a-b/index.html': 'how-to/a-b/',
                    'how_to/a_b/index.html': 'how-to/a-b/',
                    'howto/a-b/index.html': 'how-to/a-b/',
                    'howto/a_b/index.html': 'how-to/a-b/',
                },
            ),
        ],
    )
    def test_ok(self, found: set[str], expected: dict[str, str]):
        redirects = automatic_redirects._build_redirects(found)
        assert sorted(redirects.items()) == list(expected.items())

    def test_variant_as_real_page_raises(self):
        # When both separator variants are real pages, the generated alias would
        # collide with a real page -- a configuration error that should fail
        # loudly rather than silently shadowing a page.
        found = {'how-to/foo', 'how_to/foo'}
        with pytest.raises(AssertionError, match='is a real page'):
            automatic_redirects._build_redirects(found)


class TestAutomaticRedirects:
    @staticmethod
    def fake_app(
        *,
        package: str | None = None,
        rediraffe_redirects: dict[str, str] | str | None = None,
        found_docs: typing.Iterable[str] = (),
    ) -> sphinx.application.Sphinx:
        """Build a minimal fake Sphinx app/config/env for ``_automatic_redirects()``."""
        config = types.SimpleNamespace(package=package, rediraffe_redirects=rediraffe_redirects)
        env = types.SimpleNamespace(found_docs=set(found_docs))
        return types.SimpleNamespace(config=config, env=env)  # pyright: ignore[reportReturnType]

    def test_automatic_redirects_extends_dict_in_final_pass(self):
        app = self.fake_app(rediraffe_redirects={}, found_docs={'foo/a-b', 'index'})
        automatic_redirects._automatic_redirects(app, app.env)
        assert app.config.rediraffe_redirects == {'foo/a_b': 'foo/a-b'}

    def test_automatic_redirects_skips_per_package_pass(self):
        app = self.fake_app(
            package='pathops', rediraffe_redirects={}, found_docs={'foo/a-b', 'index'}
        )
        automatic_redirects._automatic_redirects(app, app.env)
        assert app.config.rediraffe_redirects == {}

    def test_automatic_redirects_preserves_existing_user_redirects(self):
        app = self.fake_app(
            rediraffe_redirects={'old/page': 'new/page'}, found_docs={'foo/a-b', 'index'}
        )
        automatic_redirects._automatic_redirects(app, app.env)
        assert app.config.rediraffe_redirects == {'old/page': 'new/page', 'foo/a_b': 'foo/a-b'}

    @pytest.mark.parametrize('value', ('redirects.txt', None))
    def test_automatic_redirects_raises_when_rediraffe_redirects_not_a_dict(
        self, value: str | None
    ):
        # The extension requires rediraffe_redirects to be a dict; a filename
        # (str) or None is a misconfiguration and should fail loudly.
        app = self.fake_app(rediraffe_redirects=value, found_docs={})
        with pytest.raises(AssertionError, match='be a dict'):
            automatic_redirects._automatic_redirects(app, app.env)

    def test_alias_clobbering_user_redirect_raises(self):
        app = self.fake_app(
            rediraffe_redirects={'how_to/manage_libraries': 'custom/target'},
            found_docs={'how-to/manage-libraries', 'index'},
        )
        with pytest.raises(ValueError, match='clobbered'):
            automatic_redirects._automatic_redirects(app, app.env)

    def test_alias_chaining_with_user_redirect_raises(self):
        app = self.fake_app(
            rediraffe_redirects={'how-to/manage-libraries': 'custom/target'},
            found_docs={'how-to/manage-libraries', 'index'},
        )
        with pytest.raises(ValueError, match='chain with manually'):
            automatic_redirects._automatic_redirects(app, app.env)

    def test_user_redirect_chaining_with_alias_raises(self):
        app = self.fake_app(
            rediraffe_redirects={'custom/alias': 'how_to/manage_libraries'},
            found_docs={'how-to/manage-libraries', 'index'},
        )
        with pytest.raises(ValueError, match='should point to'):
            automatic_redirects._automatic_redirects(app, app.env)

    def test_user_redirect_to_canonical_name_ok(self):
        app = self.fake_app(
            rediraffe_redirects={'custom/alias': 'how-to/manage-libraries'},
            found_docs={'how-to/manage-libraries', 'index'},
        )
        automatic_redirects._automatic_redirects(app, app.env)
        assert 'custom/alias' in app.config.rediraffe_redirects
        assert len(app.config.rediraffe_redirects) > 1
