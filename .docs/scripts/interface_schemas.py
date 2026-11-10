#!/usr/bin/env python3
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

r"""Print the JSON Schema of each databag defined by interface schema.py files.

Run this with the dependencies in ``schema-requirements.txt`` available, for example::

    uv run --no-project --with-requirements schema-requirements.txt \
        .docs/scripts/interface_schemas.py interfaces/smtp/interface/v0/schema.py

Prints a JSON object mapping each schema path given on the command line to either
``{"databags": {...}}`` or ``{"error": "..."}``. ``databags`` maps each of
``provider-app``, ``provider-unit``, ``requirer-app`` and ``requirer-unit`` to the
databag's JSON Schema, or to ``null`` if the databag is empty.

Two schema conventions are supported:

* Module-level ``ProviderAppData``, ``ProviderUnitData``, ``RequirerAppData`` and
  ``RequirerUnitData`` names, each a Pydantic model or ``None``.
* ``ProviderSchema`` and ``RequirerSchema`` classes with ``app`` and ``unit`` fields, as
  defined with ``interface_tester.schema_base.DataBagSchema``.

This script imports pydantic, so it is run in its own environment rather than imported by
the interface preprocessor.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import traceback
import typing

if typing.TYPE_CHECKING:
    import types


def main(argv: list[str]) -> int:
    """Print the databag JSON Schemas for each schema.py path in argv."""
    result = {path: _describe(pathlib.Path(path)) for path in argv[1:]}
    json.dump(result, sys.stdout, indent=2)  # Keep field declaration order.
    return 0


def _describe(path: pathlib.Path) -> dict[str, typing.Any]:
    try:
        module = _load(path)
        models = _databag_models(module)
        return {
            'databags': {
                name: None if model is None else model.model_json_schema()
                for name, model in models.items()
            }
        }
    except Exception:
        return {'error': traceback.format_exc()}


def _load(path: pathlib.Path) -> types.ModuleType:
    name = f'_interface_schema_{abs(hash(str(path.resolve())))}'
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # Needed for dataclasses and postponed annotations.
    spec.loader.exec_module(module)
    return module


def _databag_models(module: types.ModuleType) -> dict[str, typing.Any]:
    names = {
        'provider-app': 'ProviderAppData',
        'provider-unit': 'ProviderUnitData',
        'requirer-app': 'RequirerAppData',
        'requirer-unit': 'RequirerUnitData',
    }
    if any(hasattr(module, n) for n in names.values()):
        return {databag: getattr(module, name, None) for databag, name in names.items()}
    if hasattr(module, 'ProviderSchema') or hasattr(module, 'RequirerSchema'):
        result: dict[str, typing.Any] = {}
        for side in ('provider', 'requirer'):
            schema = getattr(module, f'{side.title()}Schema', None)
            for bag in ('app', 'unit'):
                result[f'{side}-{bag}'] = _field_model(schema, bag)
        return result
    raise ValueError(
        'schema defines neither ProviderAppData/ProviderUnitData/RequirerAppData/'
        'RequirerUnitData nor ProviderSchema/RequirerSchema'
    )


def _field_model(schema: typing.Any, field: str) -> typing.Any:
    """Return the model annotated on a DataBagSchema's app or unit field, or None."""
    if schema is None or field not in schema.model_fields:
        return None
    annotation = schema.model_fields[field].annotation
    # DataBagSchema declares `app: BaseModel | None = None`; subclasses narrow it.
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    if args:
        annotation = args[0] if len(args) == 1 else annotation
    if not hasattr(annotation, 'model_json_schema'):
        return None
    if annotation.__name__ == 'BaseModel':
        return None  # Not overridden by the subclass, so the databag is unspecified.
    return annotation


if __name__ == '__main__':
    sys.exit(main(sys.argv))
