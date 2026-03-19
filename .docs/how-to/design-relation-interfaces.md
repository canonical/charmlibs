(design-relation-interfaces)=
# How to design relation interfaces

When designing a schema for a new interface, observe the following rules.

[TBD] Why we design interfaces up front.

[TBD] Why wire format and charm-facing API are different.

[TBD] Library API for delta and holistic charms.

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

Unit tests must capture the interface schema evolution. Unit tests typically also capture the charm-facing API evolution.

When the interface is modified, running unit tests against both new and old test vectors informs the charm library developer what is extended and what is broken.
The developer then updates the unit tests encoding the conscious choice how the old data is meant to be handled.

### Fixed field types

```py
V1_FLOAT = {"number": 42.1}
V1_INT = {"number": 42}
V1_MISSING = {}

def test_field_types():
    Data.model_validate(V1_FLOAT)
    Data.model_validate(V1_INT)
    Data.model_validate(V1_MISSING)

# Note that Pydantic coerces False to 0 and "42" to 42
@pytest.mark.parametrize("bad_value", ["str", [], {}, None])
def test_invalid_field_types(bad_value: Any):
    with pytest.raises(ValueError):
        Data.model_validate({"number": bad_value})
```

### No mandatory fields

```py
V1_DATABAG = {"name": "aa", "surname": "bb"}
@pytest.mark.parametrize("field_to_remove", ["name", "surname"])
def test_missing_fields(field_to_remove):
    data = {**V1_DATABAG}
    del data[field_to_remove]
    assert DataV2.model_validate(data)
```

### No field reuse

A unit test:

```py
V1_DATABAG = {"name": "a name", "surname": "bb"}

def test_removed_fields():
    assert DataV2.model_validate(V1_DATABAG).name == "a name"
    assert "surname" not in DataV2.model_fields  # Removed in V2

    # alternatively
    assert DataV2.model_validate(V1_DATABAG).model_dump == {"name": "a name"}
```

Or a state transition test:

```py
def _on_relation_changed(self, event: ops.RelationChangedEvent):
    data = event.relation.load(lib.DataV2, event.app)
    assert data.name == "aa"

# test
data = {"name": '"aa"', "surname": '"bb"'}
rel = testing.Relation('db', remote_app_data=data)
state_in = testing.State(leader=True, relations={rel})
ctx.run(ctx.on.relation_changed(rel), state_in)
```

### Collections

```py
DATABAG = {"foos": [
    {"foo": "a"},
    {"strange-data": "bar"},
    {"foo": "b", "new-field": "d"}
]}

def test_foos():
    foos_seen_by_charm = charm_lib.parse(DATABAG).foos
    assert charm_sees = {"a", "b"}
```

### URLs and URIs

```py
@pytest.mark.parametrize("bad_url", [
    "ftp://an.example",        # unsupported scheme
    "https://1.1.1.1",         # hostnames only
    "http://user@an.example",  # credentials not allowed
    "http://an.example/#bar",  # fragment not allowed
])
def test_bad_url_field_values(bad_url: str):
    with pytest.raises(ValueError):
        SomeData(url_field=bad_url)

@pytest.mark.parametrize("good_url", [
    "http://an.example",
    "https://an.example",
    "http://an.example/some/path",
    "http://an.example/some/path?some=query",
])
def test_good_url_field_values(good_url: str)
    SomeData(url_field=good_url)
```

### Secret content schema

Using a state transition test, in essence:

```py
@pytest.mark.parametrize("secret_content, status", [
    (GOOD_SECRET_CONTENT, ops.ActiveStatus()),
    (BAD_SECRET_CONTENT, ops.WaitingStatus("...")),
])
def test_secret_content(secret_content: dict[str, Any], status):
    ...
    state_out = ctx.run(
        ctx.on.relation_changed(relation=rel, remote_unit=1), state_in)

    assert state_out.unit_status == status
```

[Full test code](https://github.com/dimaqq/op083-samples/blob/main/test_secret_content.py)

Or a unit test:

```py
GOOD_SECRET_CONTENT = {"secret_thing": "foo", "some_future_field": "42"}
BAD_SECRET_CONTENT = {"unknown_field": "42"}
DATABAG = {"server_uri": '"secret://42"'}

def test_good_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("charm_lib._load_secret", GOOD_SECRET_CONTENT)
    charm_lib.parse(DATABAG)
    assert charm_lib.get_secret_thing == "foo"

def test_bad_secret():
    monkeypatch.setattr("charm_lib._load_secret", BAD_SECRET_CONTENT)
    charm_lib.parse(DATABAG)
    with pytest.raises(SomeCharmLibError):
        charm_lib.get_secret_thing()
```

### Handle bad remote data

```py
# dummy charm
def __init__(self, framework):
    foo = FooRequirer(self, relation="foo")
    assert not foo.is_ready

# test
data = {"bad": '"data"', "weird": "[{}, {}]"}
rel = testing.Relation("foo", remote_app_data=data)
state_in = testing.State(relations={rel})
ctx.run(ctx.on.relation_changed(rel), state_in)
```


### Provide .is\_ready

```py
# dummy charm
def __init__(self, framework):
    foo = FooRequirer(self, relation="foo")
    assert foo.is_ready

# test
data = {"good": '"value"', "some-future-thing": '"sss"'}
rel = testing.Relation("foo", remote_app_data=data)
state_in = testing.State(relations={rel})
ctx.run(ctx.on.relation_changed(rel), state_in)
```

### Advanced status

```py
# dummy charm
def __init__(self, framework):
    self.foo = FooRequirer(self, relation="foo")
    ...

def _on_relation_changed(self, event: ops.RelationChangedEvent):
    if not self.foo.is_ready:
        self.unit.status = ops.WaitingStatus(self.foo.rich_status)
    try:
        host = self.foo.get_hostname()
        use(host)
    except SomeException as e:
        self.unit.status = ops.BlockedStatus(str(e)) 

# test
data = {"host": '"fe80::1"'}
rel = testing.Relation("foo", remote_app_data=data)
state_in = testing.State(relations={rel})
state_out = ctx.run(ctx.on.relation_changed(rel), state_in)
assert state_out.unit_status == ops.testing.BlockedStatus(
    "foo not ready: host must be a domain name"
)
```
