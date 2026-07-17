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

"""Generate source .rst files for lib tables, from libs.yaml in the reference directory."""

from __future__ import annotations

import pathlib
import typing
from xml.etree import ElementTree

import yaml

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

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
_SUBSTRATE_TOOLTIPS = {
    'machine': 'Compatible with machine charms.',
    'K8s': 'Compatible with Kubernetes charms.',
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
    Instead, edit libs.yaml and then rebuild the docs.

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
_TAGS_KEY_TABLE_HEADER = """.. list-table::
   :widths: 1, 100
   :header-rows: 1

   * - Tag
     - Description
"""


class _TagInfo(typing.TypedDict):
    description: str
    criteria: str


_TagsYaml = dict[str, dict[str, _TagInfo]]


class _LibEntry(typing.TypedDict, total=True):
    name: str
    status: str
    url: str
    docs: str
    src: str
    kind: str
    description: str
    tags: list[str]


class _InterfaceLibEntry(_LibEntry, total=True):
    rel_name: str
    rel_url_charmhub: str
    rel_url_schema: str


class _GeneralLibEntry(_LibEntry, total=True):
    machine: bool
    K8s: bool


class _LibsYaml(typing.TypedDict):
    general: list[_GeneralLibEntry]
    interfaces: list[_InterfaceLibEntry]


class _TableRow(typing.NamedTuple):
    status: str
    name: str
    kind: str
    description: str


def _generate_libs_tables(docs_dir: str | pathlib.Path) -> None:
    reference_dir = pathlib.Path(docs_dir) / 'reference'
    generated_dir = reference_dir / 'generated'
    generated_dir.mkdir(exist_ok=True)
    data: _LibsYaml = yaml.safe_load((reference_dir / 'libs.yaml').read_text())
    tag_descriptions = _load_tag_descriptions(reference_dir)
    interface_entries = data['interfaces']
    general_entries = data['general']
    _write_if_needed(
        path=(generated_dir / 'interface-libs-table.rst'),
        content=_get_interface_libs_table(interface_entries, tag_descriptions),
    )
    _write_if_needed(
        path=(generated_dir / 'interface-libs-status-key-table.rst'),
        content=_get_status_key_table_dropdown(interface_entries),
    )
    _write_if_needed(
        path=(generated_dir / 'general-libs-table.rst'),
        content=_get_general_libs_table(general_entries, tag_descriptions),
    )
    _write_if_needed(
        path=(generated_dir / 'general-libs-status-key-table.rst'),
        content=_get_status_key_table_dropdown(general_entries),
    )
    _write_if_needed(
        path=(generated_dir / 'interface-libs-tags-key-table.rst'),
        content=_get_tags_key_table_dropdown(
            interface_entries, tag_descriptions, column='interface'
        ),
    )
    _write_if_needed(
        path=(generated_dir / 'general-libs-tags-key-table.rst'),
        content=_get_tags_key_table_dropdown(
            general_entries, tag_descriptions, column='description'
        ),
    )


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    to_write = _FILE_HEADER + content
    if not path.exists() or path.read_text() != to_write:
        path.write_text(to_write)


def _load_tag_descriptions(reference_dir: pathlib.Path) -> dict[str, str]:
    """Load tags.yaml and return a flat mapping of tag name to description."""
    tags_data: _TagsYaml = yaml.safe_load((reference_dir / 'tags.yaml').read_text())
    tag_descriptions: dict[str, str] = {}
    for _category_key in ('domain-tags', 'audience-tags'):
        for tag_name, tag_info in tags_data.get(_category_key, {}).items():
            tag_descriptions[tag_name] = tag_info['description']
    return tag_descriptions


##########
# tables #
##########


def _get_interface_libs_table(
    entries: Iterable[_InterfaceLibEntry],
    tag_descriptions: dict[str, str],
) -> str:
    def key(row: tuple[str, ...]) -> tuple[str, ...]:
        status, _name, _kind, desc = row
        return status, desc

    rows = [
        (
            _status(entry),
            _name(entry),
            _kind(entry),
            _interface_description(entry, tag_descriptions),
        )
        for entry in entries
        if _is_listed(entry)
    ]
    return _INTERFACE_LIBS_TABLE_HEADER + _rst_rows(sorted(rows, key=key))


def _get_general_libs_table(
    entries: Iterable[_GeneralLibEntry],
    tag_descriptions: dict[str, str],
) -> str:
    def key(row: _TableRow) -> tuple[str, ...]:
        return row.status, row.kind, row.name, row.description

    rows = [
        _TableRow(
            _status(entry),
            _name(entry),
            _kind(entry),
            _general_description(entry, tag_descriptions),
        )
        for entry in entries
        if _is_listed(entry)
    ]
    return _GENERAL_LIBS_TABLE_HEADER + _rst_rows(sorted(rows, key=key))


def _get_status_key_table_dropdown(entries: Iterable[_LibEntry]) -> str:
    used_statuses = {entry['status'] for entry in entries}
    rows = [
        (_status({'status': s}), _STATUS_TOOLTIPS[s])  # type: ignore
        for s in _STATUS_SORTKEYS
        if s in _EMOJIS and s in used_statuses
    ]
    rows.append(('', 'None of the above.'))
    table = _KEY_TABLE_HEADER + _rst_rows(rows)
    return _KEY_DROPDOWN_HEADER + _indent_lines(table, level=3)


def _get_tags_key_table_dropdown(
    entries: Iterable[_LibEntry],
    tag_descriptions: dict[str, str],
    *,
    column: str,
) -> str:
    used_tags: set[str] = set()
    for entry in entries:
        if _is_listed(entry):
            used_tags.update(entry['tags'])
    if not used_tags:
        return ''
    rows = [
        (
            _rst_table_indent(_rst_raw_html(_html_tag_tooltip(f'#{tag}', None))),
            tag_descriptions.get(tag, ''),
        )
        for tag in sorted(used_tags)
    ]
    table = _TAGS_KEY_TABLE_HEADER + _rst_rows(rows)
    return _tags_key_dropdown_header(column) + _indent_lines(table, level=3)


def _tags_key_dropdown_header(column: str) -> str:
    msg = f'Tags are shown in the {column} column. See tooltips, or click here for a key.'
    return f'.. dropdown:: {msg}\n\n'


def _is_listed(entry: _LibEntry) -> bool:
    return entry['status'] != 'unlisted'


##########
# fields #
##########


def _status(entry: _LibEntry) -> str:
    status = entry['status']
    html_lines = [_html_hidden_span(_STATUS_SORTKEYS[status])]
    if status in _EMOJIS:
        html_lines.append(_html_emoji_tooltip(_EMOJIS[status], _STATUS_TOOLTIPS.get(status)))
    return _rst_table_indent(_rst_raw_html('\n'.join(html_lines)))


def _name(entry: _LibEntry) -> str:
    name = entry['name'] if entry['kind'] != 'Charmhub' else entry['name'].removeprefix('charms.')
    link = _html_link(name, entry['url'])
    extras = ', '.join(_html_link(s, url) for s in ('docs', 'src') if (url := entry[s]))
    links = f'{link} <span style="white-space:nowrap;">({extras})</span>' if extras else link
    html_lines = [_html_hidden_span(name.ljust(64, 'z')), links]
    return _rst_table_indent(_rst_raw_html('\n'.join(html_lines)))


def _kind(entry: _LibEntry) -> str:
    kind = entry['kind']
    content = [_rst_raw_html(_html_hidden_span(_KIND_SORTKEYS[kind]))]
    if kind_str := _EMOJIS.get(kind, '') + kind:
        content.append(_rst_lines(kind_str))
    return _rst_table_indent('\n'.join(content))


def _interface_description(
    entry: _InterfaceLibEntry,
    tag_descriptions: dict[str, str],
) -> str:
    sortkeys = [
        entry['rel_name'].ljust(64, 'z'),
        str(_STATUS_SORTKEYS[entry['status']]),
        entry['name'],
        str(_KIND_SORTKEYS[entry['kind']]),
    ]
    content = [_rst_raw_html(_html_hidden_span(''.join(sortkeys)))]
    if rel_links := _rel_links(entry):
        content.append(_rst_raw_html(f'<p>{rel_links}</p>'))
    if desc := entry['description']:
        content.append(_rst_lines(desc))
    if tags := entry['tags']:
        content.append(_tags_rst(tags, tag_descriptions))
    return _rst_table_indent('\n'.join(content))


def _rel_links(entry: _InterfaceLibEntry) -> str:
    if not (name := entry['rel_name']):
        return ''
    if not (main_url := entry['rel_url_charmhub']):
        return f'<span class="chip no-spellcheck">{name}</span>'
    main_link = _html_link(name, main_url)
    if not (schema_url := entry['rel_url_schema']):
        return f'<span class="chip">{main_link}</span>'
    schema_link = _html_link('schema', schema_url)
    return f'<span class="chip">{main_link}</span> ({schema_link})'


def _general_description(
    entry: _GeneralLibEntry,
    tag_descriptions: dict[str, str],
) -> str:
    substrates = ('machine', 'K8s')
    sortkeys = [
        *('0' if entry[s] else '1' for s in substrates),
        str(_STATUS_SORTKEYS[entry['status']]),
        entry['name'],
        str(_KIND_SORTKEYS[entry['kind']]),
    ]
    content = [_rst_raw_html(_html_hidden_span(''.join(sortkeys)))]
    if desc := entry['description']:
        content.append(_rst_lines(desc))
    substrate_parts = [
        _html_tag_tooltip(f'{_EMOJIS.get(s, "")}{s}', _SUBSTRATE_TOOLTIPS.get(s))
        for s in substrates
        if entry[s]
    ]
    tag_parts = [_html_tag_tooltip(f'#{t}', tag_descriptions.get(t)) for t in entry['tags']]
    if substrate_parts or tag_parts:
        joined = ' '.join(substrate_parts + tag_parts)
        content.append(_rst_raw_html(f'<span class="tag-group">{joined}</span>'))
    return _rst_table_indent('\n'.join(content))


def _tags_rst(tags: list[str], tag_descriptions: dict[str, str]) -> str:
    """Return RST raw HTML for a tags line, or empty string if no tags."""
    assert tags
    tag_htmls = [_html_tag_tooltip(f'#{t}', tag_descriptions.get(t)) for t in tags]
    joined = ' '.join(tag_htmls)
    return _rst_raw_html(f'<span class="tag-group">{joined}</span>')


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


def _html_tag_tooltip(tag_text: str, tooltip: str | None) -> str:
    e = ElementTree.Element('a', attrib={'class': 'tag-div no-spellcheck', 'href': '#'})
    e.text = tag_text
    if tooltip is not None:
        child = ElementTree.Element('span', attrib={'class': 'tag-tooltip'})
        child.text = tooltip
        e.append(child)
    return ElementTree.tostring(e, encoding='unicode')
