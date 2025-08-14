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
# ruff: noqa: S314 (unsecure xml parsing)
# ruff: noqa: S405 (unsecure xml parsing)

"""Unit tests for the 'generate' local Sphinx extension."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ElementTree

import generate_tables
import pytest
from docutils import core


def rst_to_html(rst: str) -> str:
    return core.publish_parts(rst, writer_name='html')['html_body']  # type: ignore


def test_status_key_table():
    rst = generate_tables._get_status_key_table_dropdown([])
    dropdown_contents = '\n'.join(rst.split('\n')[1:])
    html_content = rst_to_html(dropdown_contents)
    table = ElementTree.fromstring(html.unescape(html_content)).find('.//table')
    assert table is not None


@pytest.mark.parametrize('rows', ([('r1c1', 'r1c2'), ('r2c1', 'r2c2')],))
def test_rst_rows(rows: list[tuple[str, ...]]):
    rst = generate_tables._rst_rows(rows)
    html_content = rst_to_html(f'.. list-table::\n\n{rst}')
    table = ElementTree.fromstring(html_content).find('.//table')
    assert table is not None
    table_rows = table.findall('.//tr')
    assert len(table_rows) == len(rows)
    for i, row in enumerate(table_rows):
        table_cells = row.findall('.//td')
        assert len(table_cells) == len(rows[i])
        for table_cell, cell in zip(table_cells, rows[i]):
            assert table_cell.text == cell


@pytest.mark.parametrize(('emoji', 'tooltip'), [('foo', 'bar')])
def test_html_emoji_tooltip(emoji: str, tooltip: str):
    html_content = generate_tables._html_emoji_tooltip(emoji, tooltip)
    div = ElementTree.fromstring(html_content)
    assert 'emoji-div' in div.attrib['class']
    assert div.text == emoji
    _, child = div.iter()
    assert 'emoji-tooltip' in child.attrib['class']
    assert child.text == tooltip


@pytest.mark.parametrize('msg', ['foo', 1])
def test_html_hidden_div(msg: str):
    html_content = generate_tables._html_hidden_span(msg)
    span = ElementTree.fromstring(html_content)
    assert 'display:none;' in span.attrib['style']
    assert span.text == str(msg)


@pytest.mark.parametrize(('text', 'url'), [('foo', 'bar')])
def test_html_link(text: str, url: str):
    html_content = generate_tables._html_link(text, url)
    a = ElementTree.fromstring(html_content)
    assert a.attrib['href'] == url
    assert a.text == text
