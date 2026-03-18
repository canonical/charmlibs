(design-relation-interfaces)=
# How to design relation interfaces

Words words words words.

Why we design interfaces up front.

Why wire format and charm-facing API are different.

Library API for delta and holistic charms.

Using newer Pydantic, prefer the `MISSING` sentinel value over the more traditional `None`.

```py
# missing field is read as <MISSING>; deleted when written out
foo: str | MISSING = MISSING

# missing field is read as None; written out as JSON null
foo: str | None = None
```

## Databag schema

### Fixed field types

Once a field has been declared, the type of that field must not be changed.

Field types cannot be narrowed, widened or changed entirely.

Same applies to significant changes to the range of values that a field validator accepts.

Unexpected enum values should be parsed as `MISSING` or a pre-defined catch-all `UNKNOWN` value:

```py
foo: Enum(A, B) | MISSING = MISSING
bar: Enum(UNKNOWN, A, B) = UNKNOWN
```

### No mandatory fields

Top-level fields must not required or optional.

```py
foo: str | MISSING = MISSING
```

Likewise most sub-fields must be not required or optional.

```py
role: Role | MISSING = MISSING
  subject: str | MISSING = MISSING
  session: str | MISSING = MISSING
```

A default value may be used instead in some cases.

```py
protocol: Literal["http", "https"] = "https"
temperature: float = 0.0
priority: int = 100
sans_dns: frozenset[str] = frozenset()
```

### No field reuse

If a field has been removed from the interface, another field with the very same name must not be added.

The exception is reverting removal of a field, where the field is brought back with the exact same type and semantics.

### Collections

Collections must be represented as arrays of objects on the wire, with few exceptions.

Collections must be emitted in some stable order, and the order must be ignored on reception. In other words, collections are sets.

```py
class Endpoint(pydantic.BaseModel, frozen=True):
    id: str | MISSING = MISSING
    some_url: str | MISSING = MISSING


class Databag(pydantic.BaseModel):
    endpoints: frozenset[Endpoint] | MISSING = MISSING
```

Collections of primitive types are strongly discouraged.

Data maps are strongly discouraged. An exception to this rule if when the data map key is a Juju entity with a well-known string representation, such as unit name or machine id.

### URLs and URIs

URLs, URIs and URI-looking connection strings are encouraged.

Each URL field must be documented and tested for consistency and precision:

- what the purpose of the URL is
- what kind of URL it is semantically
- what components are allowed
- what values are allowed for each component

A sample checklist:

- [ ] is this a base URL, an endpoint, a full URL, an opaque identifier, or an application-specific URI or string
- [ ] limits for the URL as a whole, such as max length or allowed alphabet
- [ ] is the scheme required, optional or not allowed; what schemes are allowed
- [ ] is the userinfo required, optional or not allowed; what elements of userinfo are allowed
- [ ] is the host required, optional or not allowed; what kind of values: domain names, IPv4 addresses, and/or IPv6 addresses
- [ ] is the port required, optional or not allowed; what range of values
- [ ] is the path required, optional or not allowed; any restrictions on the path, such as max length
- [ ] is the query required, optional or not allowed; any restrictions on keys, expected treatment for duplicate keys
- [ ] is the fragment required, optional or not allowed; any restrictions, such as max length

### Semantic grouping

The databag content should be structured to reflect the meaning of data, for example:

```py
{
    "direct": {"host": ..., "port": ...},
    "upstream": {"base_url": ..., "path": ...}
}
```

### Secret content schema

When a secret is shared over a relation, the secret content schema must be contained in the same charm library as the relation interface schema.

Same rules apply to the secret content:

- no mandatory fields
- no field reuse
- allowed URL or URI components

## Charm library

To allow interface evolution, the charm-facing API should be decoupled from the interface parsing code. The Python code in the charm library typically deals with:

- logic: combining fields, filtering values
- stable Python API: both new and legacy interface fields are processed
- run-time: wrapping and suppressing errors in further dependencies and secrets
- arguments: charm context, for example the arguments that charm passes to the library
- third-party dependencies, for example loading PEM content in `cryptography.x509` primitives

Adopt the following conventions in charm libraries that wrap interfaces.

### Handle bad remote data

Initialising the charm library object, and superficial API access (`.is_ready`, detailed status: see below) must not raise exceptions due to relation databag contents.
Most importantly parsing the remote databag content must not lead to a charm-level exception / unit going into the error state.

- charm object initialisation must not raise
- charm object `.is_ready` must not raise

Relation databags should not be loaded at charm object initialisation time, but if they are, the library should catch exceptions arising from `ops.Relation.load()`.
Likewise, `.is_ready` should catch exceptions arising from loading and parsing the databags.

Exceptions can and should be used to report incorrect initialization (wrong relation name), or transient errors (unexpected hook command errors).

### Provide .is\_ready

The charm library must provide an API that quickly determines if the endpoint is "ready" for a particular purpose.
Accessing `is_ready` must be free from side effects, must not raise exceptions and the return value must be `False` in these cases:

- the relevant databag is empty, when appropriate
- the relevant databag could not be parsed
- the library evaluated the databag and determines that it's logically "not ready"

The specific shape of the API varies, here are some common examples:

- `.is_ready` property in a simple requirer
- `.is_ready(self, relation: ops.Relation)` method in an application provider
- `.is_ready(self, relation, remote_unit)` method in a per-unit provider
- `.is_foo_ready` and `.is_bar_ready` when the interface provides two functions
- `.is_request_ready` and `.is_acknowledgement_ready` when two distinct states can be expressed over the interface

### Advanced status

Charm libraries authors are advised to provide some API that reports advanced status of the wrapped endpoint.
It's reasonable for the unit to go into a waiting, blocked or degraded state on "bad" relation data. 

There's no recommendation on the specific shape of the API.
Some ideas to consider `.get_foo_status() -> ops.Status`, `.get_foo_error() -> str|None`, or `.validate_foo()` that raises exceptions.

Ultimately the charm should be able to provide additional details about unit's current status.
In the example below, "ingress not ready" is controlled by the charm, and "FQDN is missing" is a string received from the charm library through an advanced status API.

```
Waiting(ingress not ready: FDQN is missing)

charm --^^^^^^^^^^^^^^^^^
charm library -------------^^^^^^^^^^^^^^^
```

## Testing
