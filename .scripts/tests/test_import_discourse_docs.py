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

"""Unit tests for the import_discourse_docs script."""

import pathlib

import import_discourse_docs as ids
import pytest

# --- _topic_id ---


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://discourse.charmhub.io/t/tls-certificates-interface/15539', 15539),
        ('https://discourse.charmhub.io/t/some-slug/123/4', 123),  # trailing post number
        ('https://discourse.charmhub.io/t/15539', 15539),  # slug omitted
    ],
)
def test_topic_id(url: str, expected: int):
    assert ids._topic_id(url) == expected


def test_topic_id_invalid():
    with pytest.raises(ValueError, match='Not a Discourse topic URL'):
        ids._topic_id('https://charmhub.io/some-charm')


# --- _resolve_images ---


def test_resolve_images_replaces_upload_shortcodes():
    raw = 'before ![image](upload://abc123.png) after'
    cooked = '<p>before <img src="https://cdn.example/abc123.png" alt="image"> after</p>'
    result = ids._resolve_images(raw, cooked)
    assert result == 'before ![image](https://cdn.example/abc123.png) after'


def test_resolve_images_strips_dimension_suffix():
    raw = '![diagram|690x420](upload://abc.png)'
    cooked = '<img src="https://cdn.example/abc.png">'
    result = ids._resolve_images(raw, cooked)
    assert result == '![diagram](https://cdn.example/abc.png)'


def test_resolve_images_no_images_is_noop():
    raw = 'plain text with no images'
    assert ids._resolve_images(raw, '') == raw


# --- main ---


def test_main_writes_resolved_markdown(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / 'docs' / 'explanation' / 'page.md'

    def fake_fetch(topic_id: int):
        assert topic_id == 15539
        return {
            'post_stream': {
                'posts': [
                    {
                        'raw': '# Title\n\n![i](upload://x.png)',
                        'cooked': '<img src="https://cdn.example/x.png">',
                    },
                ],
            },
        }

    monkeypatch.setattr(ids, '_fetch', fake_fetch)
    monkeypatch.setattr(
        'sys.argv',
        ['import_discourse_docs.py', 'https://discourse.charmhub.io/t/slug/15539', str(out)],
    )

    ids.main()

    assert out.read_text() == '# Title\n\n![i](https://cdn.example/x.png)'
