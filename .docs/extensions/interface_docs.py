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

"""Include interface reference docs in docs site."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import typing

from sphinx.errors import ExtensionError

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _interface_docs)
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _interface_docs(app: sphinx.application.Sphinx) -> None:
    if app.config.package is not None:
        # For efficiency, don't write interface docs during the package reference docs passes.
        # But we need to make sure something is there so that the TOC glob doesn't fail.
        ref_dir = pathlib.Path(app.confdir, 'reference', 'interfaces')
        ref_dir.mkdir(parents=True, exist_ok=True)
        _write_if_needed(path=ref_dir / 'placeholder.md', content='# Temporary TOC placeholder')
        return
    _main(docs_dir=pathlib.Path(app.confdir))


####################
# generation logic #
####################

INDEX_TEMPLATE = """
({label})=
# {interface_name}

```{{toctree}}
:glob:
:reversed:
:maxdepth: 1

{interface_name}/*
```
""".strip()
REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'
# A README can contain `<!-- schema-table: schemas/provider.json -->` to have the field table for
# that schema generated at docs build time, so that the schema is the only source of truth.
SCHEMA_TABLE_MARKER = re.compile(r'<!--\s*schema-table:\s*(\S+?)\s*-->')


def _main(docs_dir: pathlib.Path) -> None:
    """Write automodule file for package and placeholders rst files for all other packages."""
    root = docs_dir.parent
    ref_dir = docs_dir / 'reference' / 'interfaces'
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / 'placeholder.md').unlink(missing_ok=True)
    cmd = [root / '.scripts/ls.py', 'interfaces', '--exclude-examples', '--exclude-placeholders']
    interfaces = json.loads(subprocess.check_output(cmd, text=True))
    for path_str in interfaces:
        interface_dir = root / path_str
        interface_name = interface_dir.name
        interface_ref_dir = ref_dir / interface_name
        interface_ref_dir.mkdir(exist_ok=True)
        label = f'interfaces-{interface_name.replace("_", "-")}'
        index = INDEX_TEMPLATE.format(label=label, interface_name=interface_name)
        _write_if_needed(path=ref_dir / f'{interface_name}.md', content=index)
        for v in (interface_dir / 'interface').glob('v[0-9]*'):
            readme_raw = _expand_schema_tables((v / 'README.md').read_text(), v)
            base_url = f'{REPO_MAIN_URL}/interfaces/{interface_name}/interface/{v.name}'
            # match all non-http(s) markdown links and prepend base_url to matching links
            readme = re.sub(
                r'\[(.+)\]\((?!https?://)([^)]+)\)',
                lambda m: f'[{m.group(1)}]({base_url}/{m.group(2)})',  # noqa: B023
                readme_raw,
            )
            content = f'({label}-{v.name})=\n' + readme
            _write_if_needed(path=interface_ref_dir / f'{v.name}.md', content=content)


def _expand_schema_tables(readme: str, version_dir: pathlib.Path) -> str:
    """Replace each schema-table marker in the README with a table generated from the schema."""

    def replace(match: re.Match[str]) -> str:
        try:
            schema = _load_schema(version_dir, match.group(1))
        except (OSError, json.JSONDecodeError, _SchemaDumpError) as e:
            raise ExtensionError(
                f'{version_dir / "README.md"}: cannot build the table for {match.group(0)}: {e}'
            ) from e
        return _schema_table(schema)

    return SCHEMA_TABLE_MARKER.sub(replace, readme)


# Run in a separate environment, so that the docs build doesn't need the schema dependencies.
_DUMP_PYDANTIC_SCHEMA = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('schema', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(getattr(module, sys.argv[2]).model_json_schema()))
"""


def _load_schema(version_dir: pathlib.Path, source: str) -> dict[str, typing.Any]:
    """Load the JSON schema named by a schema-table marker.

    The source is either a JSON schema file (`schemas/provider.json`), or a Python file and the
    name of a pydantic model in it (`schema.py:ProviderAppData`).
    """
    filename, _, model = source.partition(':')
    path = version_dir / filename
    if not model:
        return json.loads(path.read_text())
    root = pathlib.Path(__file__).parent.parent.parent
    cmd = [
        'uv', 'run', '--no-project', '--quiet',
        '--with-requirements', str(root / 'schema-requirements.txt'),
        'python', '-c', _DUMP_PYDANTIC_SCHEMA, str(path), model,
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise _SchemaDumpError(result.stderr.strip() or f'exit code {result.returncode}')
    return json.loads(result.stdout)


class _SchemaDumpError(Exception):
    """The subprocess dumping a pydantic model's schema failed; the message is its stderr."""


def _schema_table(schema: dict[str, typing.Any]) -> str:
    """Render the fields of a JSON schema as a Markdown table.

    Nested object properties and array items are flattened using dotted paths, with `[]` marking
    array items and `{...}` marking keys matched by a pattern or allowed as additional properties.
    Local `$ref`s are followed, and the alternatives of an `anyOf` or `oneOf` are merged.
    """
    rows = ['| Field | Type | Required | Description |', '| --- | --- | --- | --- |']
    # Alternatives that share a field would otherwise list it more than once.
    rows.extend(dict.fromkeys(_schema_rows(schema, root=schema, prefix='', seen=())))
    return '\n'.join(rows)


def _resolve(schema: dict[str, typing.Any], root: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """Follow a local `$ref` (to `#/$defs/...` or `#/definitions/...`), keeping sibling keys."""
    ref = schema.get('$ref')
    if not isinstance(ref, str) or not ref.startswith('#/'):
        return schema
    target: typing.Any = root
    for part in ref[2:].split('/'):
        target = target[part]
    siblings = {k: v for k, v in schema.items() if k != '$ref'}
    return {**_resolve(target, root), **siblings}


def _alternatives(
    schema: dict[str, typing.Any], root: dict[str, typing.Any]
) -> list[dict[str, typing.Any]]:
    """Return the resolved alternatives of a schema, or the schema itself if it has none."""
    if not isinstance(schema, dict):  # a boolean schema (`true` or `false`) has no fields
        return []
    schema = _resolve(schema, root)
    options = schema.get('anyOf') or schema.get('oneOf')
    if not options:
        return [schema]
    rest = {k: v for k, v in schema.items() if k not in ('anyOf', 'oneOf')}
    result: list[dict[str, typing.Any]] = []
    for option in options:
        result.extend(_alternatives({**rest, **option}, root))
    return result


def _type_names(schema: dict[str, typing.Any]) -> list[str]:
    ref = schema.get('$ref')
    if isinstance(ref, str):  # only local references are resolved, so link to anything else
        return [f'[external schema]({ref})']
    type_ = schema.get('type')
    if isinstance(type_, list):
        return [str(t) for t in type_]
    if type_:
        name = str(type_)
    elif 'enum' in schema or 'const' in schema:
        name = 'string'
    elif 'properties' in schema:
        name = 'object'
    else:
        return []
    if 'enum' in schema:
        name += ' (' + ', '.join(f'`{v}`' for v in schema['enum']) + ')'
    elif 'const' in schema:
        name += f' (`{schema["const"]}`)'
    return [name]


def _schema_rows(
    schema: dict[str, typing.Any],
    root: dict[str, typing.Any],
    prefix: str,
    seen: tuple[str, ...],
) -> list[str]:
    rows: list[str] = []
    for alternative in _alternatives(schema, root):
        required = set(alternative.get('required', []))
        children = [
            (name, prop, name in required)
            for name, prop in alternative.get('properties', {}).items()
        ]
        children.extend(
            (f'{{{pattern}}}', prop, False)
            for pattern, prop in alternative.get('patternProperties', {}).items()
        )
        additional = alternative.get('additionalProperties')
        if isinstance(additional, dict) and additional:
            children.append(('{...}', additional, False))
        for name, prop, is_required in children:
            rows.extend(_field_rows(prop, root, f'{prefix}{name}', is_required, seen))
        items = alternative.get('items')
        if not prefix and alternative.get('type') == 'array' and isinstance(items, dict):
            rows.extend(_schema_rows(items, root, prefix='[].', seen=seen))
    return rows


def _field_rows(
    prop: dict[str, typing.Any],
    root: dict[str, typing.Any],
    path: str,
    is_required: bool,
    seen: tuple[str, ...],
) -> list[str]:
    if not isinstance(prop, dict):  # a boolean schema
        prop = {}
    # A recursive schema still gets a row for the field that recurses, but isn't expanded
    # again, so the table doesn't loop forever or leave the field out.
    recurse = True
    ref = prop.get('$ref')
    if isinstance(ref, str):
        recurse = ref not in seen
        seen = (*seen, ref)
    alternatives = _alternatives(prop, root)
    types: list[str] = []
    for alternative in alternatives:
        types.extend(t for t in _type_names(alternative) if t not in types)
    description = _resolve(prop, root).get('description') or ''
    description = ' '.join(description.split()).replace('|', '\\|')
    required = 'yes' if is_required else 'no'
    rows = [f'| `{path}` | {" or ".join(types)} | {required} | {description} |']
    if not recurse:
        return rows
    for alternative in alternatives:
        items = alternative.get('items')
        if alternative.get('type') == 'array' and isinstance(items, dict):
            rows.extend(_schema_rows(items, root, prefix=f'{path}[].', seen=seen))
        else:
            rows.extend(_schema_rows(alternative, root, prefix=f'{path}.', seen=seen))
    return rows


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
