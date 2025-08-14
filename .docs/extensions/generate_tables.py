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

# ruff: noqa: S405 (suspicious-xml-etree-import )

"""Generate source .rst files for lib tables, from CSV files in the reference directory."""

from __future__ import annotations

import csv
import pathlib
import re
import typing
from xml.etree import ElementTree

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    from typing import Iterable

    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _generate)
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _generate(app: sphinx.application.Sphinx):
    _generate_libs_tables(app.confdir)


####################
# Table generation #
####################


_EMOJIS = {
    # status
    'recommended': '✅',
    'dep': '↪️',
    'experimental': '⚗️',
    'legacy': '🚫',
    'team': '💬',
    # substrate
    'machine': '🖥️',
    'K8s': '☸️',
}
_STATUS_TOOLTIPS = {
    'recommended': 'Recommended for use in new charms today!',
    'dep': 'Dependency of other libs, unlikely to be required directly.',
    'experimental': 'Experimental, use at your own risk!',
    'legacy': 'Deprecated library, not recommended for use in new charms.',
    'team': 'Team internal lib, may not be stable for external use.',
}
_KIND_SORTKEYS = {'PyPI': 0, 'git': 1, 'Charmhub': 2, '': 3}
_STATUS_SORTKEYS = {
    status: priority
    for priority, status in enumerate([
        'recommended',
        '',
        'dep',
        'experimental',
        'team',
        'legacy',
    ])
}
_FILE_HEADER = """..
    This file was automatically generated.
    It should not be manually edited!
    Instead, edit the corresponding -raw.csv file and then rebuild the docs.

"""
_INTERFACE_LIBS_TABLE_HEADER = """.. list-table::
   :class: sphinx-datatable
   :widths: 1, 40, 1, 60
   :header-rows: 1

   * -
     - Library
     - Kind
     - Interface
"""
_GENERAL_LIBS_TABLE_HEADER = """.. list-table::
   :class: sphinx-datatable
   :widths: 1, 40, 1, 60
   :header-rows: 1

   * -
     - Library
     - Kind
     - Description
"""
_KEY_TABLE_HEADER = """.. list-table::
   :widths: 1, 100
   :header-rows: 1

   * -
     - Description
"""
_KEY_MSG = 'Library status is shown in the left column. See tooltips, or click here for a key.'
_KEY_DROPDOWN_HEADER = f""".. dropdown:: {_KEY_MSG}

"""


class _CSVRow(typing.TypedDict, total=True):
    name: str
    status: str
    url: str
    docs: str
    src: str
    kind: str
    description: str


class _InterfaceCSVRow(_CSVRow, total=True):
    rel_name: str
    rel_url_charmhub: str
    rel_url_schema: str


class _GeneralCSVRow(_CSVRow, total=True):
    machine: str
    K8s: str


class _TableRow(typing.NamedTuple):
    status: str
    name: str
    kind: str
    description: str


def _generate_libs_tables(docs_dir: str | pathlib.Path) -> None:
    reference_dir = pathlib.Path(docs_dir) / 'reference'
    generated_dir = reference_dir / 'generated'
    generated_dir.mkdir(exist_ok=True)
    # interface libs
    with (reference_dir / 'interface-libs.csv').open() as f:
        interface_entries: list[_InterfaceCSVRow] = list(csv.DictReader(f))  # type: ignore
    _write_if_needed(
        path=(generated_dir / 'interface-libs-table.rst'),
        content=_get_interface_libs_table(interface_entries),
    )
    _write_if_needed(
        path=(generated_dir / 'interface-libs-status-key-table.rst'),
        content=_get_status_key_table_dropdown(interface_entries),
    )
    # general libs
    with (reference_dir / 'general-libs.csv').open() as f:
        general_entries: list[_GeneralCSVRow] = list(csv.DictReader(f))  # type: ignore
    _write_if_needed(
        path=(generated_dir / 'general-libs-table.rst'),
        content=_get_general_libs_table(general_entries),
    )
    _write_if_needed(
        path=(generated_dir / 'general-libs-status-key-table.rst'),
        content=_get_status_key_table_dropdown(general_entries),
    )


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    to_write = _FILE_HEADER + content
    if not path.exists() or path.read_text() != to_write:
        path.write_text(to_write)


##########
# tables #
##########


def _get_interface_libs_table(entries: Iterable[_InterfaceCSVRow]) -> str:
    def key(row: tuple[str, ...]) -> tuple[str, ...]:
        status, _name, _kind, desc = row
        return status, desc

    rows = [
        (_status(entry), _name(entry), _kind(entry), _interface_description(entry))
        for entry in entries
        if _is_listed(entry)
    ]
    return _INTERFACE_LIBS_TABLE_HEADER + _rst_rows(sorted(rows, key=key))


def _get_general_libs_table(entries: Iterable[_GeneralCSVRow]) -> str:
    def key(row: _TableRow) -> tuple[str, ...]:
        return row.status, row.kind, row.name, row.description

    rows = [
        _TableRow(_status(entry), _name(entry), _kind(entry), _general_description(entry))
        for entry in entries
        if _is_listed(entry)
    ]
    return _GENERAL_LIBS_TABLE_HEADER + _rst_rows(sorted(rows, key=key))


def _get_status_key_table_dropdown(entries: Iterable[_CSVRow]) -> str:
    used_statuses = {entry['status'] for entry in entries}
    rows = [
        (_status({'status': s}), _STATUS_TOOLTIPS[s])  # type: ignore
        for s in _STATUS_SORTKEYS
        if s in _EMOJIS and s in used_statuses
    ]
    rows.append(('', 'None of the above.'))
    table = _KEY_TABLE_HEADER + _rst_rows(rows)
    return _KEY_DROPDOWN_HEADER + _indent_lines(table, level=3)


def _is_listed(row: _CSVRow) -> bool:
    return row['status'] != 'unlisted'


##########
# fields #
##########


def _status(entry: _CSVRow) -> str:
    status = entry['status']
    html_lines = [_html_hidden_span(_STATUS_SORTKEYS[status])]
    if status in _EMOJIS:
        html_lines.append(_html_emoji_tooltip(_EMOJIS[status], _STATUS_TOOLTIPS.get(status)))
    return _rst_table_indent(_rst_raw_html('\n'.join(html_lines)))


def _name(entry: _CSVRow) -> str:
    name = entry['name'] if entry['kind'] != 'Charmhub' else _charmcraft_namespaced_name(entry)
    link = _html_link(name, entry['url'])
    extras = ', '.join(_html_link(s, url) for s in ('docs', 'src') if (url := entry[s]))
    links = f'{link} <span style="white-space:nowrap;">({extras})</span>' if extras else link
    html_lines = [_html_hidden_span(name.ljust(64, 'z')), links]
    return _rst_table_indent(_rst_raw_html('\n'.join(html_lines)))


def _charmcraft_namespaced_name(entry: _CSVRow) -> str:
    lib_name = entry['name']
    match = re.search(r'charmhub\.io/([^/]+)/', entry['url'])
    assert match is not None
    charm = match.group(1)
    namespace = charm.replace('-', '_')
    return f'{namespace}.{lib_name}'


def _kind(entry: _CSVRow) -> str:
    kind = entry['kind']
    content = [_rst_raw_html(_html_hidden_span(_KIND_SORTKEYS[kind]))]
    if kind_str := _EMOJIS.get(kind, '') + kind:
        content.append(_rst_lines(kind_str))
    return _rst_table_indent('\n'.join(content))


def _interface_description(entry: _InterfaceCSVRow) -> str:
    sortkeys = [
        entry['rel_name'].ljust(64, 'z'),
        str(_STATUS_SORTKEYS[entry['status']]),
        entry['name'],
        str(_KIND_SORTKEYS[entry['kind']]),
    ]
    html_lines = [_html_hidden_span(''.join(sortkeys))]
    if rel_links := _rel_links(entry):
        html_lines.append(rel_links)
    content = [_rst_raw_html('\n'.join(html_lines))]
    if desc := entry['description']:
        content.append(_rst_lines(desc))
    return _rst_table_indent('\n'.join(content))


def _rel_links(entry: _InterfaceCSVRow) -> str:
    if not (name := entry['rel_name']):
        return ''
    if not (main_url := entry['rel_url_charmhub']):
        return _html_no_spellcheck_span(name)
    main_link = _html_link(name, main_url)
    if not (schema_url := entry['rel_url_schema']):
        return main_link
    schema_link = _html_link('schema', schema_url)
    return f'{main_link} ({schema_link})'


def _general_description(entry: _GeneralCSVRow) -> str:
    substrates = ('machine', 'K8s')
    sortkeys = [
        *('0' if entry[s] else '1' for s in substrates),
        str(_STATUS_SORTKEYS[entry['status']]),
        entry['name'],
        str(_KIND_SORTKEYS[entry['kind']]),
    ]
    content = [_rst_raw_html(_html_hidden_span(''.join(sortkeys)))]
    if firstline := ' '.join(_EMOJIS.get(s, '') + s for s in substrates if entry[s]):
        content.append(_rst_lines(firstline))
    if desc := entry['description']:
        content.append(_rst_lines(desc))
    return _rst_table_indent('\n'.join(content))


#######
# rst #
#######


def _rst_rows(rows: Iterable[tuple[str, ...]]) -> str:
    lines: list[str] = []
    for row in rows:
        first, *rest = (f' {cell}' if cell and not cell.startswith('\n') else cell for cell in row)
        lines.append(f'   * -{first}\n')
        lines.extend(f'     -{line}\n' for line in rest)
    return ''.join(lines)


def _rst_raw_html(html: str) -> str:
    return f"""
.. raw:: html

{_indent_lines(html, level=3)}
"""


def _rst_lines(text: str) -> str:
    return '\n'.join(f'| {line}' if line else '|' for line in text.split('\n'))


def _rst_table_indent(text: str) -> str:
    return _indent_lines(text, level=7)


def _indent_lines(text: str, *, level: int) -> str:
    indent = ' ' * level
    return '\n'.join(f'{indent}{line}' if line else '' for line in text.split('\n'))


########
# html #
########


def _html_emoji_tooltip(emoji: str, tooltip: str | None) -> str:
    e = ElementTree.Element('div', attrib={'class': 'emoji-div'})
    e.text = emoji
    if tooltip is not None:
        child = ElementTree.Element('div', attrib={'class': 'emoji-tooltip'})
        child.text = tooltip
        e.append(child)
    return ElementTree.tostring(e, encoding='unicode')


def _html_hidden_span(text: object) -> str:
    e = ElementTree.Element('span', attrib={'style': 'display:none;', 'class': 'no-spellcheck'})
    e.text = str(text)
    return ElementTree.tostring(e, encoding='unicode')


def _html_link(text: str, url: str) -> str:
    for char in ('.', '-', '_'):
        text = text.replace(char, f'{char}<wbr>')
    return f'<a href="{url}" class="no-spellcheck">{text}</a>'


def _html_no_spellcheck_span(text: object) -> str:
    e = ElementTree.Element('span', attrib={'class': 'no-spellcheck'})
    e.text = str(text)
    return ElementTree.tostring(e, encoding='unicode')
