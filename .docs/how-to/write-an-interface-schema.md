---
myst:
  html_meta:
    description: Write the schema that describes an interface's relation data, and share it with the interface library that implements it.
---

(how-to-write-an-interface-schema)=
# How to write an interface schema

Every interface definition should be accompanied by a `schema.py`, which describes how the serialized relation data on the wire is transformed into meaningful objects.
This document explains how to format the schema.
To learn how to design the relation data format, read {ref}`design-relation-interfaces`.

## Name all four databags

A relation has four databags, and a schema must account for every one of them, using exactly these names:

| Name | Databag |
|------|---------|
| `ProviderAppData` | The provider's application databag. |
| `ProviderUnitData` | The provider's unit databag. |
| `RequirerAppData` | The requirer's application databag. |
| `RequirerUnitData` | The requirer's unit databag. |

Any that aren't used by a specific interface must be explicitly set to `None`, like this:

```py
class ProviderAppData:
    ...

ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
```

Each model that isn't `None` must be a class that can be passed to [`ops.Relation.load`](https://canonical.com/juju/docs/ops/latest/reference/ops-module/#ops.Relation.load) and successfully load all permitted relation data for this interface.
`Relation.load` requires Ops 2.23 or later.
It's common to use a [Pydantic](https://docs.pydantic.dev/) `BaseModel` subclass, but a standard library dataclass works if you want to avoid the dependency.

```py
import pydantic


class Receiver(pydantic.BaseModel):
    """A single endpoint the provider is listening on."""

    protocol: str
    url: str


class ProviderAppData(pydantic.BaseModel):
    """The provider's application databag."""

    receivers: list[Receiver] | None = pydantic.Field(
        default=None,
        description='Endpoints the provider accepts traces on.',
        examples=[[{'protocol': 'otlp_http', 'url': 'http://tempo:4318'}]],
    )
```

The `ProviderAppData` class can then be used to deserialize the relation data:

```py
data = event.relation.load(ProviderAppData, event.app)
```

Fill in `description` and `examples` on each field.
An example is a value of the field as the model holds it, so `6379` rather than the `'6379'` on the wire, and CI uses it to test the schema.

## Say how the values are encoded, if it isn't JSON

Ops decodes each databag value as JSON by default.
If that describes your interface, you don't need to do anything extra here.
If you use a different format, for example writing strings as bare (rather than JSON-encoded) strings, you'll need to define custom encoder and decoder functions.

If you define them as `__juju_encoder__` and `__juju_decoder__` on the databag model, then Charmlibs CI will automatically pass them through to `Relation.load` when validating the schema, like this:

```py
data = event.relation.load(
    ProviderAppData, event.app, decoder=ProviderAppData.__juju_decoder__
)
relation.save(data, self.app, encoder=ProviderAppData.__juju_encoder__)
```

If all four databags use the same encoder and decoder, you can reduce repetition by defining them on a common base class.
This base class defines a decoder that passes the databag value through unmodified.
It does this because its values are string which it 'encodes' by passing them through unmodified as well, other than setting `''` for `None` (which erases the value from the databag).

```py
class _BareStringDatabag:
    @staticmethod
    def __juju_decoder__(value: str) -> str:
        """Pass Juju's string through unmodified.

        We'll decode it with individual field validators.
        """
        return value

    @staticmethod
    def __juju_encoder__(value: str | None) -> str:
        """Convert `None` to "", erasing the value; return other values unmodified.

        We assume they're always a string. Ops will error on a non-string.
        """
        return '' if value is None else value
```

### Databags with mixed encodings

Some databags have mixed encodings, for example using JSON encoding for lists and objects, but writing strings without encoding.
This can be handled using Pydantic's `field_validator` and `field_serializer` decorators to determine per-field behaviour.
Decorated methods are called automatically for the appropriate fields when Ops creates or serializes a Pydantic model.

```py
import json
from typing import Any


class ProviderAppData(_BareStringDatabag, pydantic.BaseModel):
    """The provider's application databag."""

    model_config = pydantic.ConfigDict(validate_by_name=True)

    endpoints: str | None = pydantic.Field(
        default=None,
        description='Comma-separated host:port pairs, as a bare string.',
        examples=['10.0.0.1:6379,10.0.0.2:6379'],
    )
    port: int | None = pydantic.Field(
        default=None,
        description='The port to connect on, as a bare string.',
        examples=[6379],
    )
    requested_secrets: list[str] | None = pydantic.Field(
        default=None,
        alias='requested-secrets',
        description='Secret fields the requirer needs, as a JSON array.',
        examples=[['username', 'password']],
    )

    @pydantic.field_validator('requested_secrets', mode='before')
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @pydantic.field_serializer('requested_secrets')
    def _dump_json(self, value: list[str] | None) -> str | None:
        return None if value is None else json.dumps(value)

    @pydantic.field_serializer('port')
    def _dump_str(self, value: int | None) -> str | None:
        return None if value is None else str(value)
```

Pydantic converts a bare string to the field's type when the model is loaded, so a bare-string field can still be an `int`, `bool`, or enum, like `port`.
Ops only saves strings, so give each such field a serializer that converts it back.

Set `validate_by_name=True` in any model with aliased fields, so that charm code can write `ProviderAppData(requested_secrets=[...])`.
Without it, that call doesn't raise an error -- Pydantic ignores the unrecognized argument, and the field keeps its default.
`validate_by_name` requires Pydantic 2.11 or later, and earlier versions ignore it just as quietly, so declare `pydantic>=2.11` wherever the model is used.

## Depend on Pydantic and the standard library only

A schema is imported with Pydantic and the standard library available, and nothing else. Keeping it that way is what lets the schema be read on its own, by tooling and by people, and lets a library adopt it as its own databag models without dragging in test dependencies.

(interface-schema-in-library)=
## Share the schema with the library

When an interface has a library in this repo, the schema and the library's databag models should describe the same wire format.
Keeping two copies in sync is a job nobody wants.
Instead, put the models in the library as a private `_schema.py` module and make the interface's `schema.py` a symlink to it:

```text
interfaces/<interface>/
├── interface/
│   └── v<N>/
│       ├── interface.yaml
│       ├── README.md
│       └── schema.py -> ../../src/charmlibs/interfaces/<interface>/_schema.py
└── src/charmlibs/interfaces/<interface>/
    ├── __init__.py      # Export the package's public API.
    ├── _<interface>.py  # Library logic, importing from `._schema`.
    └── _schema.py       # The single source of truth for databag models.
```

## Validate your work

CI checks the schema of every interface against the format described here.
It also builds an instance of each model, saves it to a databag with `Relation.save`, and checks that `Relation.load` gives it back unchanged.
Each field's value is taken from its `examples`, or generated from its type if it has none, and this applies to the fields of nested models too.
A generated value fails if a validator needs something more specific, so a field like that needs an example.
To check as you work, run:

```bash
just interface-schemas                   # Check all interfaces.
just interface-schemas tls-certificates  # Check named interfaces.
```

```{note}
Only the latest version of each interface is checked. Older versions are kept for reference and are not held to this format.
```
