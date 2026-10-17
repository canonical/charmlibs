#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "ops[testing]>=2.23",
#     "polyfactory>=2",
#     "pydantic~=2.0",
# ]
# ///

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

"""Check that interface schemas comply with the documented format.

Only the latest version of each interface is checked -- older versions are retained for
reference until they're removed, and are not held to the current format.

The schema format is documented in `.docs/how-to/write-an-interface-schema.md`. In short, a
schema module defines all four of `ProviderAppData`, `ProviderUnitData`, `RequirerAppData` and
`RequirerUnitData`. Each is either a model usable with `ops.Relation.load` and
`ops.Relation.save`, or `None` to say that databag is always empty.

All four are required, rather than letting an absent name mean "empty", so that an empty databag
is a decision someone made and a reviewer can see, and so that a misspelled name is an error
rather than a silently empty databag.

Each model must be a Pydantic `BaseModel` subclass or a dataclass -- the two shapes `ops`
documents as supported. Each is then exercised with `ops` itself: an instance is saved to a
databag with `Relation.save`, loaded back with `Relation.load` and saved again, and both saves
must write the same databag. The
instance is generated from the field types with `polyfactory`, using a field's `examples` instead
wherever it has them, including on the fields of nested models. Generated values can't satisfy
every validator (a pattern on a nested dataclass, say), so a field like that needs examples.

A model may also carry a `__juju_decoder__`/`__juju_encoder__` pair, describing how this
interface's databag values are encoded. Omitting them means JSON, which is what `ops` does by
default. They are needed for interfaces whose databags hold bare strings rather than JSON, which
is most of the data-platform family. `ops` does not read these names yet, so callers pass them
explicitly: `relation.load(ProviderAppData, app, decoder=ProviderAppData.__juju_decoder__)`.

The schema modules are imported with Pydantic and the standard library available, and nothing
else -- `ops` and the other dependencies of this script are blocked while a schema is imported.
That is deliberate: a schema is a dependency-light description of a wire format, so that
anything can read it, and so that a library can adopt it as its own databag model.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import pathlib
import subprocess
import sys
import typing

import ops
import pydantic
from ops import testing
from polyfactory.factories import DataclassFactory
from polyfactory.factories.pydantic_factory import ModelFactory

if typing.TYPE_CHECKING:
    import types

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_LS = _REPO_ROOT / '.scripts' / 'ls.py'

#: Models every schema must define, in the order they're reported.
MODEL_NAMES = ('ProviderAppData', 'ProviderUnitData', 'RequirerAppData', 'RequirerUnitData')
#: Names from the retired `pytest-interface-tester` format, rejected so they can't creep back in.
LEGACY_NAMES = ('ProviderSchema', 'RequirerSchema')
#: The optional codec a model may carry, describing how its databag values are encoded.
CODEC_NAMES = ('__juju_decoder__', '__juju_encoder__')
#: Top-level packages this script needs but schemas must not, blocked while a schema is imported.
BLOCKED_IMPORTS = ('ops', 'polyfactory', 'faker')
#: Interfaces not checked yet, each waiting on a pending PR. Remove an entry when its PR lands.
SKIP = {
    'azure_service_principal': 'pending #661',
    'azure_storage': 'pending #661',
    's3': 'pending #661',
    'postgresql_client': 'pending #671',
    'cos_agent': 'pending #746',
    'dns_record': 'pending #745',
    'openfga': 'pending #744',
    'kratos_external_idp': 'pending #742',
}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description='Check that interface schemas comply with the documented format.'
    )
    parser.add_argument(
        'interface',
        nargs='*',
        help='Interface names to check, e.g. `tracing`. Defaults to every interface.',
    )
    args = parser.parse_args()
    schemas = _schemas(args.interface)
    if not schemas:
        print('No interfaces with a schema matched.', file=sys.stderr)
        return 1
    failures = skipped = 0
    for name, path in schemas:
        if name in SKIP:
            skipped += 1
            print(f'skip {name} ({SKIP[name]})')
            continue
        problems = _check(path)
        if problems:
            failures += 1
            print(f'FAIL {name} ({path})')
            for problem in problems:
                print(f'       {problem}')
        else:
            print(f'ok   {name}')
    checked = len(schemas) - skipped
    print(f'\n{checked - failures}/{checked} interface schemas comply with the format.')
    if skipped:
        print(f'{skipped} skipped, see `SKIP` in {pathlib.Path(__file__).name}.')
    if failures:
        print('See `.docs/how-to/write-an-interface-schema.md` for the format.')
    return 1 if failures else 0


def _schemas(interfaces: list[str]) -> list[tuple[str, pathlib.Path]]:
    """Return (interface name, schema path) for each interface, latest version only.

    Interfaces without a schema are skipped. `ls.py` resolves the latest version for us, so this
    keeps working when the versioned interface directories are flattened.
    """
    cmd = [str(_LS), 'interfaces', '--output', 'name', '--output', 'schema_path']
    entries = json.loads(subprocess.check_output(cmd, text=True, cwd=_REPO_ROOT))
    wanted = set(interfaces)
    return [
        (entry['name'], _REPO_ROOT / entry['schema_path'])
        for entry in entries
        if entry['schema_path'] and (not wanted or entry['name'] in wanted)
    ]


def _check(path: pathlib.Path) -> list[str]:
    """Return a list of format problems with the schema at `path`, empty if it complies."""
    try:
        module = _import(path)
    except Exception as e:  # Report any import failure rather than crashing.
        hint = ''
        if isinstance(e, ModuleNotFoundError) and e.name == 'interface_tester':
            hint = ' -- schemas must not depend on `pytest-interface-tester`'
        return [f'failed to import: {type(e).__name__}: {e}{hint}']
    problems: list[str] = [
        f'defines `{name}`, from the retired interface tester format'
        for name in LEGACY_NAMES
        if hasattr(module, name)
    ]
    missing = [name for name in MODEL_NAMES if not hasattr(module, name)]
    if missing:
        joined = ', '.join(f'`{name}`' for name in missing)
        problems.append(f'does not define {joined} -- set to `None` for an empty databag')
    for name in MODEL_NAMES:
        if hasattr(module, name):
            problems.extend(_check_model(name, getattr(module, name)))
    problems.extend(
        f'defines a module-level `{name}`; the codec now lives on the model as '
        f'`__juju_decoder__`/`__juju_encoder__`'
        for name in ('decode', 'encode')
        if hasattr(module, name)
    )
    return problems


def _check_codec(name: str, model: type[object]) -> list[str]:
    """Return problems with a model's optional codec, empty if it doesn't declare one."""
    defined = [codec for codec in CODEC_NAMES if hasattr(model, codec)]
    if not defined:
        return []  # This interface encodes its databag values as JSON, like `ops` does by default.
    problems = [
        f'`{name}.{codec}` is not callable'
        for codec in defined
        if not callable(getattr(model, codec))
    ]
    if len(defined) == 1:
        missing = next(codec for codec in CODEC_NAMES if codec not in defined)
        problems.append(
            f'`{name}` declares `{defined[0]}` but not `{missing}` -- '
            f'a codec describes both directions'
        )
    return problems


def _check_model(name: str, model: object) -> list[str]:
    """Return problems with a single model, empty if it can be used with `ops.Relation.load`."""
    if model is None:  # This databag is always empty.
        return []
    if not isinstance(model, type):
        return [f'`{name}` is {type(model).__name__}, not a class']
    cls: type[object] = model
    if issubclass(cls, pydantic.BaseModel):
        problems = _check_codec(name, cls) + [
            f'`{name}.{field}` is annotated with `pydantic.Json`, which `ops` cannot load or save'
            for field, info in cls.model_fields.items()
            # Pydantic hoists the marker out of `Annotated` into the field metadata for a
            # required field, but leaves it in the annotation for an optional one.
            if _has_json_marker(info.annotation) or any(map(_has_json_marker, info.metadata))
        ]
    elif dataclasses.is_dataclass(cls):
        problems = []
    else:
        return [f'`{name}` is neither a Pydantic `BaseModel` subclass nor a dataclass']
    return problems or _check_round_trip(name, cls)


def _check_round_trip(name: str, model: type[object]) -> list[str]:
    """Return problems saving an instance of `model` with `ops` and loading it back."""
    hint = ' -- add or fix `examples` on the fields involved'
    try:
        instance = _generate(model)
    except Exception as e:
        return [f"`{name}`: couldn't build an instance ({_summary(e)}){hint}"]
    result: dict[str, typing.Any] = {'stage': 'saving'}

    class Charm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            framework.observe(self.on.start, self._on_start)

        def _on_start(self, _: ops.StartEvent):
            relation = self.model.get_relation('schema')
            assert relation is not None
            encoder = getattr(model, '__juju_encoder__', None)
            relation.save(instance, self.app, encoder=encoder)
            result['saved'] = dict(relation.data[self.app])
            result['stage'] = 'loading'
            decoder = getattr(model, '__juju_decoder__', None)
            loaded = relation.load(model, self.app, decoder=decoder)
            result['stage'] = 'saving the loaded'
            relation.data[self.app].clear()
            relation.save(loaded, self.app, encoder=encoder)
            result['resaved'] = dict(relation.data[self.app])

    meta = {'name': 'schema-check', 'requires': {'schema': {'interface': 'schema'}}}
    ctx = testing.Context(Charm, meta=meta)
    state = testing.State(leader=True, relations={testing.Relation('schema')})
    try:
        ctx.run(ctx.on.start(), state)
    except testing.errors.UncaughtCharmError as e:
        error = _summary(e.__cause__ or e)
        return [f'`{name}`: failed {result["stage"]} an instance ({error}){hint}']
    # Compare databags, not instances: an untyped field (a plain `dict`, say) can hold a
    # generated value, like a `datetime`, that legitimately loads back as a string.
    if result['resaved'] != result['saved']:
        return [
            f'`{name}`: saving what it loaded wrote {result["resaved"]}, '
            f'not the original {result["saved"]}'
        ]
    return []


def _generate(model: type[object]) -> object:
    """Generate an instance of `model` with a fixed seed, using field examples where given."""
    if issubclass(model, pydantic.BaseModel):
        factory = ModelFactory.create_factory(model, __use_examples__=True)
    else:
        # Dataclasses have no standard way to declare examples.
        factory = DataclassFactory.create_factory(model)
    factory.seed_random(0)
    return factory.build()


def _summary(error: BaseException) -> str:
    """Return the type and first line of `error`, or its first error for a `ValidationError`."""
    if isinstance(error, pydantic.ValidationError):
        first = error.errors()[0]
        location = '.'.join(map(str, first['loc']))
        return f'{location}: {first["msg"]}' if location else first['msg']
    lines = str(error).splitlines()
    return f'{type(error).__name__}: {lines[0]}' if lines else type(error).__name__


def _has_json_marker(annotation: object) -> bool:
    """Return whether `pydantic.Json` appears anywhere in this annotation.

    `Relation.load` decodes a databag value before handing it to the model, and `Relation.save`
    encodes what the model gives back. A `Json` field expects to do that decoding itself, so it
    receives an already-decoded value and rejects it, and it cannot be constructed from a real
    value in order to be saved. Annotate the decoded type instead.
    """
    cls = type(annotation)
    if cls.__module__.startswith('pydantic') and cls.__name__ == 'Json':
        return True
    return any(_has_json_marker(arg) for arg in typing.get_args(annotation))


def _import(path: pathlib.Path) -> types.ModuleType:
    """Import the schema at `path` under a unique module name."""
    # e.g. interfaces/tracing/interface/v2/schema.py -> schema_tracing_v2
    parts = path.relative_to(_REPO_ROOT).parts
    module_name = f'schema_{parts[1]}_{parts[3]}'.replace('-', '_')
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'could not load {path} as a Python module')
    module = importlib.util.module_from_spec(spec)
    # Register before executing, so that dataclasses and Pydantic can resolve the module.
    sys.modules[module_name] = module
    # A `None` entry in `sys.modules` makes importing that name raise `ImportError`.
    modules = typing.cast('dict[str, types.ModuleType | None]', sys.modules)
    blocked = {name: modules.get(name) for name in BLOCKED_IMPORTS}
    modules.update(dict.fromkeys(BLOCKED_IMPORTS))
    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in blocked.items():
            if original is None:
                del modules[name]
            else:
                modules[name] = original
    return module


if __name__ == '__main__':
    sys.exit(_main())
