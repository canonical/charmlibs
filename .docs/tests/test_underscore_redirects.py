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

# ruff: noqa: D103 (function docstrings)

"""Unit tests for the `underscore_redirects` local Sphinx extension."""

from __future__ import annotations

import types
import typing

import underscore_redirects

if typing.TYPE_CHECKING:
    import sphinx.application


# --- _separator_variant ---


def test_separator_variant_hyphens_to_underscores():
    assert underscore_redirects._separator_variant('how-to/manage-libraries') == (
        'how_to/manage_libraries'
    )


def test_separator_variant_underscores_to_hyphens():
    assert (
        underscore_redirects._separator_variant('reference/interfaces/fiveg_core_gnb/v1')
        == 'reference/interfaces/fiveg-core-gnb/v1'
    )


def test_separator_variant_mixed_segment():
    # A segment with both separators is a true involution.
    variant = underscore_redirects._separator_variant('foo-bar_baz/qux')
    assert variant == 'foo_bar-baz/qux'
    assert underscore_redirects._separator_variant(variant) == 'foo-bar_baz/qux'


def test_separator_variant_no_separators_returns_none():
    assert underscore_redirects._separator_variant('index') is None
    assert underscore_redirects._separator_variant('reference/v1') is None


def test_separator_variant_is_involution():
    for docname in [
        'how-to/manage-libraries',
        'reference/interfaces/fiveg_core_gnb/v1',
        'a-b_c/d-e_f',
        'index',
    ]:
        variant = underscore_redirects._separator_variant(docname)
        if variant is None:
            assert docname == 'index'
            continue
        assert underscore_redirects._separator_variant(variant) == docname


# --- _build_redirects ---


def test_build_redirects_hyphenated_page_gets_underscore_alias():
    found = {'how-to/manage-libraries', 'index'}
    redirects = underscore_redirects._build_redirects(found)
    assert redirects == {'how_to/manage_libraries': 'how-to/manage-libraries'}


def test_build_redirects_underscored_page_gets_hyphen_alias():
    found = {'reference/interfaces/fiveg_core_gnb/v1', 'index'}
    redirects = underscore_redirects._build_redirects(found)
    assert redirects == {
        'reference/interfaces/fiveg-core-gnb/v1': 'reference/interfaces/fiveg_core_gnb/v1'
    }


def test_build_redirects_both_variants_present_no_redirect():
    # When both separator variants are real pages, neither shadows the other.
    found = {'how-to/foo', 'how_to/foo'}
    assert underscore_redirects._build_redirects(found) == {}


def test_build_redirects_no_separators_no_redirects():
    assert underscore_redirects._build_redirects({'index', 'reference/v1'}) == {}


def test_build_redirects_is_pure_function():
    # _build_redirects is a pure function over found_docs; it doesn't know
    # about user-configured redirects. Merge protection lives in _populate
    # (see test_populate_does_not_overwrite_user_redirect_with_generated).
    found = {'how-to/manage-libraries', 'index'}
    assert underscore_redirects._build_redirects(found) == {
        'how_to/manage_libraries': 'how-to/manage-libraries'
    }


# --- _populate (integration with config) ---


def _make_app(
    *,
    package: str | None = None,
    rediraffe_redirects: dict[str, str] | str | None = None,
    found_docs: typing.Iterable[str] = (),
) -> sphinx.application.Sphinx:
    """Build a minimal fake Sphinx app/config/env for ``_populate()``."""
    config = types.SimpleNamespace(
        package=package,
        rediraffe_redirects=rediraffe_redirects,
    )
    env = types.SimpleNamespace(found_docs=set(found_docs))
    return typing.cast(
        'sphinx.application.Sphinx',
        types.SimpleNamespace(config=config, env=env),
    )


def _rediraffe_redirects(app: sphinx.application.Sphinx) -> dict[str, str] | str | None:
    return typing.cast('types.SimpleNamespace', app.config).rediraffe_redirects


def test_populate_extends_dict_in_final_pass():
    app = _make_app(
        rediraffe_redirects={},
        found_docs={'how-to/manage-libraries', 'index'},
    )
    underscore_redirects._populate(app, app.env)
    assert _rediraffe_redirects(app) == {'how_to/manage_libraries': 'how-to/manage-libraries'}


def test_populate_skips_per_package_pass():
    app = _make_app(
        package='pathops',
        rediraffe_redirects={},
        found_docs={'how-to/manage-libraries', 'index'},
    )
    underscore_redirects._populate(app, app.env)
    assert _rediraffe_redirects(app) == {}


def test_populate_preserves_existing_user_redirects():
    app = _make_app(
        rediraffe_redirects={'old/page': 'new/page'},
        found_docs={'how-to/manage-libraries', 'index'},
    )
    underscore_redirects._populate(app, app.env)
    redirects = _rediraffe_redirects(app)
    assert isinstance(redirects, dict)
    assert redirects['old/page'] == 'new/page'
    assert redirects['how_to/manage_libraries'] == 'how-to/manage-libraries'


def test_populate_noop_when_rediraffe_redirects_not_a_dict():
    # If rediraffe_redirects is a filename (str) or None, don't clobber it.
    for value in (None, 'redirects.txt'):
        app = _make_app(
            rediraffe_redirects=value,
            found_docs={'how-to/manage-libraries', 'index'},
        )
        underscore_redirects._populate(app, app.env)
        assert _rediraffe_redirects(app) is value


def test_populate_does_not_overwrite_user_redirect_with_generated():
    # A user-configured redirect for a variant that would also be generated
    # must be preserved.
    app = _make_app(
        rediraffe_redirects={'how_to/manage_libraries': 'custom/target'},
        found_docs={'how-to/manage-libraries', 'index'},
    )
    underscore_redirects._populate(app, app.env)
    redirects = _rediraffe_redirects(app)
    assert isinstance(redirects, dict)
    assert redirects['how_to/manage_libraries'] == 'custom/target'


# --- setup ---


def test_setup_returns_metadata():
    def _connect(*args: object, **kwargs: object) -> None:
        pass

    metadata = underscore_redirects.setup(
        typing.cast('sphinx.application.Sphinx', types.SimpleNamespace(connect=_connect))
    )
    assert metadata['version'] == '1.0.0'
    assert metadata['parallel_read_safe'] is True
    assert metadata['parallel_write_safe'] is True
