#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# ///

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

"""Generate interface reference docs in the Sphinx source tree.

Walks every interface returned by ``.scripts/ls.py interfaces``, and for each
one writes an index stub with a glob toctree under ``reference/interfaces/``,
plus one page per ``interface/v[0-9]*/README.md`` with relative links
rewritten to absolute GitHub URLs. Where a version has a ``schema.py``, its
page also gets relation data tables and a direction diagram generated from the
schema. Any warning makes the script exit with an error once every page is written.

Run from ``just docs``; see ``docs.just`` for the invocation.

This is a standalone preprocessor script and nothing here needs to be run
inside a Sphinx build. Generating the pages once up front — instead of in a
``builder-inited`` hook on every Sphinx pass — keeps the per-package
intermediate passes cheap and the extension machinery simple. The companion
``interface_docs`` extension is a fallback: it writes a placeholder page when
this script hasn't run, so the glob toctree in ``reference/interfaces.md``
still matches at least one document.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import typing

_DOCS_DIR = pathlib.Path(__file__).parent.parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
_REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'


class _Logger:
    """Print warnings to stderr, counting them so that the script can fail at the end."""

    def __init__(self) -> None:
        self.count = 0

    def warning(self, msg: str, *args: object) -> None:
        self.count += 1
        print(f'WARNING: {msg % args}', file=sys.stderr)


logger = _Logger()

_INDEX_TEMPLATE = """
({label})=
# {interface_name}

```{{toctree}}
:glob:
:reversed:
:maxdepth: 1

{interface_name}/*
```
""".strip()


def _main() -> None:
    """Write an index stub and rewritten version READMEs for every interface."""
    cmd = [
        _REPO_ROOT / '.scripts' / 'ls.py',
        'interfaces',
        '--exclude-examples',
        '--exclude-placeholders',
    ]
    interfaces: list[str] = json.loads(subprocess.check_output(cmd, text=True))
    interface_dirs = [_REPO_ROOT / path_str for path_str in interfaces]
    if missing := _missing_readmes(interface_dirs):
        paths = '\n'.join(f'  {p.relative_to(_REPO_ROOT)}' for p in missing)
        sys.exit(
            'Every interface version directory needs a README.md, '
            f'which is used as its reference page. Missing:\n{paths}'
        )
    ref_dir = _DOCS_DIR / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / 'placeholder.md').unlink(missing_ok=True)
    schema_paths = sorted(
        str(p.relative_to(_REPO_ROOT))
        for interface_dir in interface_dirs
        for p in (interface_dir / 'interface').glob('v[0-9]*/schema.py')
    )
    schemas = _load_schemas(root=_REPO_ROOT, schema_paths=schema_paths)
    for interface_dir in interface_dirs:
        _generate_interface_docs(interface_dir=interface_dir, ref_dir=ref_dir, schemas=schemas)
    if logger.count:
        sys.exit(f'{logger.count} warning(s) while generating the interface reference docs.')


def _missing_readmes(interface_dirs: list[pathlib.Path]) -> list[pathlib.Path]:
    """Return the README.md path of every interface version directory that lacks one."""
    return [
        v / 'README.md'
        for interface_dir in interface_dirs
        for v in sorted((interface_dir / 'interface').glob('v[0-9]*'))
        if not (v / 'README.md').is_file()
    ]


def _generate_interface_docs(
    interface_dir: pathlib.Path,
    ref_dir: pathlib.Path,
    schemas: dict[str, Databags | SchemaError] | None = None,
) -> None:
    """Write the index stub and rewritten version READMEs for one interface."""
    interface_name = interface_dir.name
    interface_ref_dir = ref_dir / interface_name
    interface_ref_dir.mkdir(exist_ok=True)
    label = f'interfaces-{interface_name.replace("_", "-")}'
    index = _INDEX_TEMPLATE.format(label=label, interface_name=interface_name)
    _write_if_needed(path=ref_dir / f'{interface_name}.md', content=index)
    for v in (interface_dir / 'interface').glob('v[0-9]*'):
        readme_raw = (v / 'README.md').read_text()
        if schemas:
            schema = schemas.get(str((v / 'schema.py').relative_to(_REPO_ROOT)))
            readme_path = (v / 'README.md').relative_to(_REPO_ROOT)
            readme_raw = with_generated_sections(readme_path, readme_raw, schema)
        base_url = f'{_REPO_MAIN_URL}/interfaces/{interface_name}/interface/{v.name}'
        readme = _rewrite_links(readme_raw, base_url)
        content = f'({label}-{v.name})=\n' + readme
        _write_if_needed(path=interface_ref_dir / f'{v.name}.md', content=content)


def _rewrite_links(content: str, base_url: str) -> str:
    """Rewrite relative markdown links to absolute GitHub URLs under ``base_url``."""
    relative_link = (
        r'\[(.+?)\]'  # [link text] -- capture group 1, non-greedy for multiple links on a line
        r'\('  # (
        r'(?!https?://)'  # not an absolute URL
        r'([^)]+)'  # relative target -- capture group 2
        r'\)'  # )
    )
    return re.sub(
        relative_link,
        lambda m: f'[{m.group(1)}]({base_url}/{m.group(2)})',
        content,
    )


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this script
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


#########################################
# relation data generated from schema.py #
#########################################

DATABAGS = {
    'provider-app': 'Provider application databag',
    'provider-unit': 'Provider unit databag',
    'requirer-app': 'Requirer application databag',
    'requirer-unit': 'Requirer unit databag',
}
_SCHEMA_SCRIPT = pathlib.Path(__file__).parent / 'interface_schemas.py'

# A JSON Schema, as produced by Pydantic's model_json_schema().
JsonSchema = dict[str, typing.Any]


class SchemaError(Exception):
    """A schema.py couldn't be loaded; the message is the reason."""


Databags = dict[str, JsonSchema | None]


def _load_schemas(
    root: pathlib.Path, schema_paths: list[str]
) -> dict[str, Databags | SchemaError]:
    """Return the databag JSON Schemas for each schema.py, keyed by path relative to root.

    The schemas are imported in a separate environment with the dependencies from
    schema-requirements.txt, so that pydantic isn't needed in the docs environment.
    A schema that can't be loaded maps to a SchemaError with the reason. If the schemas
    can't be loaded at all, the result is empty, with a warning.
    """
    if not schema_paths:
        return {}
    cmd = [
        'uv',
        'run',
        '--no-project',
        '--with-requirements',
        str(root / 'schema-requirements.txt'),
        str(_SCHEMA_SCRIPT),
        *schema_paths,
    ]
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, cwd=root, check=False)
        if process.returncode != 0:
            reason = process.stderr.strip() or f'exit code {process.returncode}'
            raise SchemaError(f'{_SCHEMA_SCRIPT.name} failed:\n{reason}')
        output = json.loads(process.stdout)
    except (OSError, ValueError, SchemaError) as e:
        logger.warning(
            'Could not load the interface schemas, so no relation data is generated: %s', e
        )
        return {}
    return {
        path: SchemaError(schema['error']) if 'error' in schema else schema['databags']
        for path, schema in output.items()
    }


def with_generated_sections(
    readme_path: pathlib.Path, readme: str, databags: Databags | SchemaError | None
) -> str:
    """Return the README with the generated sections added, if there is a schema.

    If the schema couldn't be loaded or rendered, warn, naming the README and the reason,
    and return the README unchanged.
    """
    if databags is None:
        return readme
    if isinstance(databags, SchemaError):
        reason = f'could not load schema.py:\n{databags}'
    else:
        try:
            return add_generated_sections(readme, databags)
        except Exception as e:  # Any malformed schema.
            reason = f'could not render schema.py: {type(e).__name__}: {e}'
    logger.warning('%s: relation data not generated, because it %s', readme_path, reason)
    return readme


def add_generated_sections(readme: str, databags: Databags) -> str:
    """Add the relation data tables and the direction diagram generated from the schema.

    The tables go directly under the 'Relation data' heading, or in a new section at the end
    if there isn't one. The diagram goes at the end of the 'Direction' section, or at the
    start of the generated relation data if there isn't one.
    """
    diagram = render_direction_diagram(databags)
    lines = readme.splitlines()
    headings = _level_2_headings(lines)
    direction = headings.get('direction')
    relation_data = render_relation_data(
        databags,
        link_schema='schema.py' not in readme,
        diagram=diagram if direction is None else '',
    )
    relation_data_index = headings.get('relation data')
    if relation_data_index is None:
        lines.extend(['', '## Relation data', '', relation_data])
    else:
        lines[relation_data_index + 1 : relation_data_index + 1] = ['', relation_data]
    if direction is not None and diagram:
        end = _section_end(lines, direction)
        while end > direction + 1 and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = ['', diagram]
    return '\n'.join(lines) + '\n'


def _level_2_headings(lines: list[str]) -> dict[str, int]:
    """Map lowercased '## ' headings outside code fences to their line index."""
    result: dict[str, int] = {}
    for i, line in _lines_outside_fences(lines):
        if line.startswith('## '):
            result.setdefault(line[3:].strip().lower(), i)
    return result


def _section_end(lines: list[str], start: int) -> int:
    """Return the index of the first '# ' or '## ' heading after start, or len(lines)."""
    for i, line in _lines_outside_fences(lines):
        if i > start and (line.startswith('# ') or line.startswith('## ')):
            return i
    return len(lines)


def _lines_outside_fences(lines: list[str]) -> typing.Iterator[tuple[int, str]]:
    fence: str | None = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        marker = re.match(r'(`{3,}|~{3,})', stripped)
        if marker:
            if fence is None:
                fence = marker.group(1)
            elif stripped.startswith(fence) and not stripped[len(fence) :].strip():
                fence = None
            continue
        if fence is None:
            yield i, line


def render_direction_diagram(databags: dict[str, JsonSchema | None]) -> str:
    """Return a mermaid diagram of which side writes which fields, or '' if nothing is written."""
    edges: list[str] = []
    for side, other in (('provider', 'requirer'), ('requirer', 'provider')):
        parts: list[str] = []
        for bag in ('app', 'unit'):
            schema = databags.get(f'{side}-{bag}')
            if schema is None:
                continue
            fields = list(_databag_model(schema).get('properties', {}))
            if fields:
                rows = [', '.join(fields[i : i + 3]) for i in range(0, len(fields), 3)]
                parts.append(f'{bag}: ' + ',<br>'.join(rows))
        if parts:
            label = '<br>'.join(parts).replace('"', '#quot;')
            edges.append(f'    {side} -->|"{label}"| {other}')
    if not edges:
        return ''
    return '\n'.join([
        '```mermaid',
        'flowchart LR',
        '    provider[Provider]',
        '    requirer[Requirer]',
        *edges,
        '```',
    ])


_NESTED_REQUIRED_NOTE = (
    'For a nested object, Required means required whenever the object is present.'
)


def render_relation_data(
    databags: dict[str, JsonSchema | None], link_schema: bool = True, diagram: str = ''
) -> str:
    """Return Markdown with a table per non-empty databag, and one per nested object.

    If diagram is given, it goes before the tables (after the schema link, if any).
    """
    out: list[str] = []
    if link_schema:
        out.extend(['Generated from the [Pydantic schema](schema.py).', ''])
    if diagram:
        out.extend([diagram, ''])
    empty = [title for name, title in DATABAGS.items() if databags.get(name) is None]
    rendered: set[str] = set()
    noted_required = False
    for name, title in DATABAGS.items():
        schema = databags.get(name)
        if schema is None:
            continue
        defs: dict[str, JsonSchema] = schema.get('$defs', {})
        if '$ref' in schema:
            # The databag model itself, so a field that refers back to it isn't a nested model.
            rendered.add(schema['$ref'].rsplit('/', 1)[-1])
        schema = _databag_model(schema)
        out.extend([f'### {title}', '', *_fields_table(schema, defs), ''])
        pending = _nested_models(schema, defs)
        while pending:
            model = pending.pop(0)
            if model in rendered:
                continue
            out.extend([f'#### `{model}`', ''])
            if not noted_required:
                # The first nested object's table, so say what its Required column means.
                out.extend([_NESTED_REQUIRED_NOTE, ''])
                noted_required = True
            rendered.add(model)
            out.extend([*_fields_table(defs[model], defs), ''])
            pending.extend(_nested_models(defs[model], defs))
    if empty:
        names = [t.removesuffix(' databag').lower() for t in empty]
        out.append(f'Empty databags: {", ".join(names)}.')
    return '\n'.join(out).strip()


def _databag_model(schema: JsonSchema) -> JsonSchema:
    """Return the object schema for a databag.

    Pydantic puts a model that refers to itself in `$defs`, and the databag's schema is then
    only a `$ref` to it.
    """
    if '$ref' in schema and 'properties' not in schema:
        return {**_resolve(schema, schema.get('$defs', {})), '$defs': schema.get('$defs', {})}
    return schema


def _fields_table(schema: JsonSchema, defs: dict[str, JsonSchema]) -> list[str]:
    properties: dict[str, JsonSchema] = schema.get('properties', {})
    if not properties:
        return ['No fields are defined.']
    required = set(schema.get('required', []))
    rows = ['| Field | Type | Required | Description |', '|---|---|---|---|']
    for field, prop in properties.items():
        if field in required:
            req = 'yes'
        elif 'default' in prop and prop['default'] is not None:
            req = f'no (default {_code(prop["default"])})'
        else:
            req = 'no'
        description = prop.get('description', '')
        if not description and '$ref' in prop:
            description = _resolve(prop, defs).get('description', '')
        type_ = _type(prop, defs).replace('|', '\\|')
        req = req.replace('|', '\\|')
        rows.append(f'| `{field}` | {type_} | {req} | {_cell(description)} |')
    return rows


def _type(schema: JsonSchema, defs: dict[str, JsonSchema]) -> str:
    if '$ref' in schema:
        target = _resolve(schema, defs)
        name = schema['$ref'].rsplit('/', 1)[-1]
        if 'enum' in target:
            return _enum(target['enum'], target)
        if target.get('type') == 'object' and 'properties' in target:
            return f'`{name}` object'
        return _type(target, defs)
    if 'anyOf' in schema or 'oneOf' in schema:
        options: list[JsonSchema] = schema.get('anyOf', schema.get('oneOf', []))
        nullable = any(o.get('type') == 'null' for o in options)
        types = [_type(o, defs) for o in options if o.get('type') != 'null']
        text = ' or '.join(dict.fromkeys(types)) or 'null'
        return f'{text} or null' if nullable and types else text
    if 'allOf' in schema and len(schema['allOf']) == 1:
        return _type(schema['allOf'][0], defs)
    if 'const' in schema:
        return _enum([schema['const']], schema)
    if 'enum' in schema:
        return _enum(schema['enum'], schema)
    if schema.get('contentMediaType') == 'application/json':
        return f'JSON-encoded {_type(schema.get("contentSchema", {}), defs)}'
    type_ = schema.get('type')
    if type_ == 'array':
        items = schema.get('items')
        if not items:
            return 'list'
        item = _type(items, defs)
        if item.startswith('one of ') or ', one of ' in item:
            return f'list, each {item}'
        return f'list of {item}s' if item.endswith(' object') else f'list of {item}'
    if type_ == 'object':
        patterns = schema.get('patternProperties')
        if isinstance(patterns, dict) and patterns:
            patterns = typing.cast('dict[str, JsonSchema]', patterns)
            mappings = [
                f'matching `{pattern}` to {_type(values, defs)}'
                for pattern, values in patterns.items()
            ]
            return 'mapping of string ' + ', or '.join(mappings)
        values = schema.get('additionalProperties')
        if isinstance(values, dict) and values:
            return f'mapping of string to {_type(typing.cast("JsonSchema", values), defs)}'
        return 'object'
    if isinstance(type_, str):
        return _with_constraints(type_, schema)
    return 'any'


# Pydantic's JSON Schema format names that don't read well as they are.
_FORMATS = {
    'ipvanyaddress': 'IP address',
    'ipvanyinterface': 'IP interface',
    'ipvanynetwork': 'IP network',
    'uri': 'URI',
    'uuid': 'UUID',
}


def _with_constraints(type_: str, schema: JsonSchema) -> str:
    text = type_
    if 'format' in schema:
        text += f' ({_FORMATS.get(schema["format"], schema["format"])})'
    if 'minimum' in schema and 'maximum' in schema:
        text += f', {schema["minimum"]} to {schema["maximum"]}'
    else:
        bounds = [
            f'{words} {schema[key]}'
            for key, words in (
                ('minimum', 'at least'),
                ('exclusiveMinimum', 'more than'),
                ('maximum', 'at most'),
                ('exclusiveMaximum', 'less than'),
            )
            if key in schema
        ]
        if bounds:
            text += ', ' + ' and '.join(bounds)
    if 'minLength' in schema:
        text += f', at least {_characters(schema["minLength"])}'
    if 'maxLength' in schema:
        text += f', at most {_characters(schema["maxLength"])}'
    if 'pattern' in schema:
        text += f', matching `{schema["pattern"]}`'
    return text


def _characters(n: int) -> str:
    return '1 character' if n == 1 else f'{n} characters'


def _enum(values: list[typing.Any], schema: JsonSchema) -> str:
    """Describe an enum or const.

    The values are shown as code, which looks the same for `1` and `"1"`, so a type other
    than string is named, taken from the values if the schema doesn't give one.
    """
    type_ = schema.get('type')
    if isinstance(type_, str):
        type_name = type_
    else:
        type_name = ' or '.join(dict.fromkeys(_json_type(v) for v in values))
    if len(values) == 1:
        code = _code(values[0])
        return code if type_name in ('string', 'null') else f'{type_name} {code}'
    text = 'one of ' + ', '.join(_code(v) for v in values)
    return text if type_name == 'string' else f'{type_name}, {text}'


def _json_type(value: typing.Any) -> str:
    """Return the JSON Schema type name of a value."""
    if value is None:
        return 'null'
    if isinstance(value, bool):  # Before int, since bool is a subclass of int.
        return 'boolean'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'number'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, dict):
        return 'object'
    return 'string'


def _code(value: typing.Any) -> str:
    """Format a JSON value as inline code, without quotes around non-empty strings."""
    if isinstance(value, str) and value:
        return f'`{value}`'
    return f'`{json.dumps(value)}`'


def _resolve(schema: JsonSchema, defs: dict[str, JsonSchema]) -> JsonSchema:
    return defs.get(schema['$ref'].rsplit('/', 1)[-1], {})


def _nested_models(schema: JsonSchema, defs: dict[str, JsonSchema]) -> list[str]:
    """Return the $defs object models referenced directly by schema's properties, in order."""
    found: list[str] = []

    def walk(node: typing.Any) -> None:
        if isinstance(node, dict):
            node = typing.cast('JsonSchema', node)
            ref = node.get('$ref')
            if isinstance(ref, str):
                name = ref.rsplit('/', 1)[-1]
                target = defs.get(name, {})
                if 'properties' in target and name not in found:
                    found.append(name)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in typing.cast('list[typing.Any]', node):
                walk(value)

    walk(schema.get('properties', {}))
    return found


def _cell(text: str) -> str:
    """Make text safe for a single Markdown table cell."""
    text = ' '.join(text.split())
    return text.replace('|', '\\|').replace('<', '&lt;')


if __name__ == '__main__':
    _main()
