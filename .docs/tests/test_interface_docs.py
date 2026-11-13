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

"""Unit tests for generating schema tables in the 'interface_docs' local Sphinx extension."""

from __future__ import annotations

import json
import subprocess
import typing

import interface_docs
import pytest
from sphinx.errors import ExtensionError

if typing.TYPE_CHECKING:
    import pathlib

SCHEMA = {
    'required': ['jobs'],
    'properties': {
        'jobs': {
            'type': 'array',
            'description': 'The jobs.',
            'items': {
                'required': ['job-id'],
                'properties': {
                    'job-id': {'type': 'string', 'description': 'An id | with a pipe.'},
                    'status': {'type': ['string', 'null'], 'title': 'Status'},
                },
            },
        },
    },
}


def test_schema_table():
    assert interface_docs._schema_table(SCHEMA).splitlines() == [
        '| Field | Type | Required | Description |',
        '| --- | --- | --- | --- |',
        '| `jobs` | array | yes | The jobs. |',
        '| `jobs[].job-id` | string | yes | An id \\| with a pipe. |',
        '| `jobs[].status` | string or null | no |  |',
    ]


def test_expand_schema_tables(tmp_path: pathlib.Path):
    (tmp_path / 'schemas').mkdir()
    (tmp_path / 'schemas' / 'provider.json').write_text(json.dumps(SCHEMA))
    readme = 'Before\n<!-- schema-table: schemas/provider.json -->\nAfter\n'
    result = interface_docs._expand_schema_tables(readme, tmp_path)
    assert result.startswith('Before\n| Field |')
    assert result.endswith('|\nAfter\n')


def test_expand_schema_tables_without_marker(tmp_path: pathlib.Path):
    assert interface_docs._expand_schema_tables('# Hello\n', tmp_path) == '# Hello\n'


def _rows(schema: dict[str, typing.Any]) -> list[str]:
    return interface_docs._schema_table(schema).splitlines()[2:]


def test_schema_table_follows_local_refs():
    schema = {
        'properties': {'error': {'$ref': '#/$defs/Error', 'description': 'What went wrong.'}},
        'required': ['error'],
        '$defs': {
            'Error': {
                'type': 'object',
                'properties': {'code': {'type': 'integer', 'description': 'The code.'}},
            },
        },
    }
    assert _rows(schema) == [
        '| `error` | object | yes | What went wrong. |',
        '| `error.code` | integer | no | The code. |',
    ]


def test_schema_table_merges_optional_alternatives():
    # pydantic renders `Optional[Model]` as an `anyOf` of the model and null.
    schema = {
        'properties': {
            'caps': {
                'anyOf': [{'$ref': '#/$defs/Caps'}, {'type': 'null'}],
                'description': 'Capabilities.',
            },
        },
        '$defs': {'Caps': {'type': 'object', 'properties': {'ip': {'type': 'boolean'}}}},
    }
    assert _rows(schema) == [
        '| `caps` | object or null | no | Capabilities. |',
        '| `caps.ip` | boolean | no |  |',
    ]


def test_schema_table_shared_fields_listed_once():
    schema = {
        'oneOf': [
            {'properties': {'a': {'type': 'string'}}},
            {'properties': {'a': {'type': 'string'}, 'b': {'type': 'string'}}},
        ],
    }
    assert _rows(schema) == ['| `a` | string | no |  |', '| `b` | string | no |  |']


def test_schema_table_pattern_and_additional_properties():
    schema = {
        'properties': {
            'units': {
                'type': 'object',
                'patternProperties': {'^unit/[0-9]+$': {'type': 'string'}},
            },
            'extra': {'type': 'object', 'additionalProperties': {'type': 'integer'}},
            'open': {'type': 'object', 'additionalProperties': True},
        },
    }
    assert _rows(schema) == [
        '| `units` | object | no |  |',
        '| `units.{^unit/[0-9]+$}` | string | no |  |',
        '| `extra` | object | no |  |',
        '| `extra.{...}` | integer | no |  |',
        '| `open` | object | no |  |',
    ]


def test_schema_table_enum_external_ref_and_boolean_schema():
    schema = {
        'properties': {
            'kind': {'enum': ['a', 'b']},
            'storage': {'oneOf': [{'$ref': 'https://example.com/s3.json'}]},
            'anything': True,
        },
    }
    assert _rows(schema) == [
        '| `kind` | string (`a`, `b`) | no |  |',
        '| `storage` | [external schema](https://example.com/s3.json) | no |  |',
        '| `anything` |  | no |  |',
    ]


def test_schema_table_enum_type_comes_from_its_values():
    schema = {
        'properties': {
            'level': {'enum': [1, 2]},
            'version': {'const': 3},
            'mixed': {'enum': ['auto', 0]},
        },
    }
    assert _rows(schema) == [
        '| `level` | integer (`1`, `2`) | no |  |',
        '| `version` | integer (`3`) | no |  |',
        '| `mixed` | string or integer (`auto`, `0`) | no |  |',
    ]


def test_schema_table_stops_on_recursion():
    schema = {
        'properties': {'node': {'$ref': '#/$defs/Node'}},
        '$defs': {
            'Node': {'type': 'object', 'properties': {'child': {'$ref': '#/$defs/Node'}}},
        },
    }
    assert _rows(schema) == [
        '| `node` | object | no |  |',
        '| `node.child` | object | no |  |',
    ]


def test_load_schema_from_pydantic_model(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(SCHEMA), stderr='')

    monkeypatch.setattr(interface_docs.subprocess, 'run', run)
    assert interface_docs._load_schema(tmp_path, 'schema.py:ProviderAppData') == SCHEMA
    (cmd,) = calls
    assert cmd[:3] == ['uv', 'run', '--no-project']
    assert cmd[-2:] == [str(tmp_path / 'schema.py'), 'ProviderAppData']
    assert any(arg.endswith('schema-requirements.txt') for arg in cmd)


def test_bad_marker_names_the_readme(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / 'empty.json').write_text('')

    def run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, stdout='', stderr='AttributeError: Nope')

    monkeypatch.setattr(interface_docs.subprocess, 'run', run)
    cases = {
        'missing.json': 'missing.json',
        'empty.json': 'Expecting value',
        'schema.py:Nope': 'AttributeError: Nope',
    }
    for source, reason in cases.items():
        with pytest.raises(ExtensionError) as excinfo:
            interface_docs._expand_schema_tables(f'<!-- schema-table: {source} -->', tmp_path)
        message = str(excinfo.value)
        assert str(tmp_path / 'README.md') in message
        assert f'schema-table: {source}' in message
        assert reason in message
