(design-relation-interfaces)=
# How to design relation interfaces
% Based on: OP083 - Relation Interface Design

When designing the relation data format for a new interface, observe the following rules.

Relation data outlives a single charm revision: either side of the relation may be upgraded first, and the upgrade itself is not atomic. The same applies to secret content when a Juju secret is shared over a relation.
Plan for the interface to evolve without causing breaking changes or downtime during application upgrades.

The relation data format is a long-lived contract, while the charm-facing API is easier to change.
Keep the two separate from the start.

When an interface evolves, some version of a library has to support both the old and new schema, and that complexity should not leak into charm code.

First, decide what data needs to be transmitted over a relation. Then design the JSON representation with provisions for backward and forward compatibility.

New interface libraries should use `pydantic ~ 2.12; ops ~= 3.6; pyright ~ 1.1.402`, and prefer the `MISSING` sentinel value over the more traditional `None`. Note that such libraries can only be used by charms based on Ubuntu 22.04 or newer.

```py
# missing field is read as <MISSING>; deleted when written out
foo: str | MISSING = MISSING

# missing field is read as None; written out as JSON null
foo: str | None = None
```

Unit tests must capture the interface schema evolution. Unit tests typically also capture the charm-facing API evolution.

When the interface is modified, running unit tests against both new and old test vectors shows the charm library developer what has been extended and what has been broken.
The developer then updates the unit tests to encode the deliberate choice for how the old data is meant to be handled.

## Design the relation data format

The only changes allowed on a published interface are:

- adding a new field, at the top level or nested: this is a new feature that must be communicated by a minor version bump of the library.
- removing a field: this is a backward-incompatible change, and must be clearly communicated by a major version bump of the library.
- tweaking field validators or extending or narrowing an enumeration value range: must be done with extra care, including compatibility testing between the old and new versions of the library.

### Fixed field types

Once a field has been declared, the type of that field must not be changed.

Field types cannot be narrowed, widened, or changed entirely, because such a field would fail to validate in either the newer or older application.

The same applies to significant changes to the range of values that a field validator accepts. For example:

- narrowing the set of allowed protocols from any value to HTTP and HTTPS is probably a bug fix, if other protocols such as FTP could not be used by the workload
- extending an IP address field to accept IPv6 addresses represents a breaking change, because the older remote application is likely to reject the value, potentially making the interface unusable
- narrowing an IP address field by removing IPv4 addresses represents a breaking change, because if the older remote application sends them, this side of the relation is likely to reject the value, potentially making the interface unusable

Unexpected enumeration values should be treated as missing (deserialised as `<MISSING>`) or coerced to a pre-defined catch-all `UNKNOWN` value:

```py
class FooEnum(StrEnum):
    A = "A"
    B = "B"

foo: FooEnum | MISSING = MISSING


class BarEnum(StrEnum):
    UNKNOWN = "UNKNOWN"
    A = "A"
    B = "B"

bar: BarEnum = BarEnum.UNKNOWN
```

The allowed field types should be validated with a unit test, for example:

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

Top-level fields must not be mandatory. Any and all top-level fields may be absent in the relation data, and it must still parse cleanly.

This implies that the empty relation data must have a valid representation in the interface model.
In practice, use a single model for both reading and writing.
Apart from `<MISSING>`, that means the writer will naturally materialise the model's default values when writing the relation data.
Readers must therefore handle both representations: a field may be absent, or it may be present with the default value.

For new interfaces, prefer representing an absent field as `<MISSING>`.
This makes absence explicit in the model, and a field that is still `<MISSING>` will be cleared again when the relation data is written.

```py
foo: str | MISSING = MISSING
```

Within a given interface, use a single missing-value convention throughout: either all `<MISSING>` or all `None`.

```py
foo: str | None = None
```

At the top level, avoid other in-domain defaults.
Top-level fields should normally use the interface's chosen missing-value convention: `<MISSING>` for newer interfaces, or `None` for older ones.

Likewise, most nested fields should be either not required, optional, or supplied with a schema-assigned in-domain value.

```py
role: Role | MISSING = MISSING
subject: str | MISSING = MISSING
session: str | MISSING = MISSING
```

Assign a concrete in-domain value in the schema only when the interface semantics define that value unambiguously and all implementations should treat it the same way.
This is appropriate for nested special enum-like or otherwise tightly defined cases, but should be uncommon.

Further examples of such schema-assigned values:

```py
protocol: Literal["http", "https"] = "https"
temperature: float = 0.0
priority: int = 100
sans_dns: frozenset[str] = frozenset()
```

The charm library implementation must be accompanied by unit tests that show:

- the empty relation data is parsed correctly
- data with missing values parses correctly for not-required fields
- data with `null` values parses correctly for optional fields
- any schema-assigned in-domain values are applied deliberately and consistently

```py
V1_DATABAG = {"name": "aa", "surname": "bb"}


def test_empty_databag():
    assert DataV2.model_validate({})


@pytest.mark.parametrize("field_to_remove", ["name", "surname"])
def test_missing_fields(field_to_remove):
    data = {**V1_DATABAG}
    del data[field_to_remove]
    assert DataV2.model_validate(data)
```

### No field reuse

If a field has been removed from the interface, another field with the very same name must not be added. This rule exists to make field removal possible without the risk of misinterpretation when two applications from different eras are integrated.

The exception is reverting removal of a field, where the field is brought back with the exact same type and semantics.

Field reuse must be prevented, either by keeping a unit test after removal:

```py
V1_DATABAG = {"name": "a name", "surname": "a surname"}

def test_removed_fields():
    assert DataV2.model_validate(V1_DATABAG).name == "a name"
    assert "surname" not in DataV2.model_fields  # Removed in V2

    # alternatively
    assert DataV2.model_validate(V1_DATABAG).model_dump == {"name": "a name"}
```

Or an equivalent state transition test:

```py
def _on_relation_changed(self, event: ops.RelationChangedEvent):
    data = event.relation.load(lib.DataV2, event.app)
    assert ...

# test
data = {"name": '"a name"', "surname": '"a surname"'}
rel = testing.Relation('endpoint', remote_app_data=data)
state_in = testing.State(leader=True, relations={rel})
ctx.run(ctx.on.relation_changed(rel), state_in)
```

### Collections

Collections must be represented as arrays of objects on the wire when using the default JSON serialisation.

Collections must be emitted in a stable order, so that setting the same data does not trigger interface bounce. The order must be ignored on reception, and the recipient is expected to discard duplicates. In other words, collections are sets.

```py
class Endpoint(pydantic.BaseModel, frozen=True):
    id: str | MISSING = MISSING
    some_url: str | MISSING = MISSING


class Databag(pydantic.BaseModel):
    endpoints: frozenset[Endpoint] | MISSING = MISSING
```

Collections of primitive types are strongly discouraged.

Data maps are strongly discouraged. An exception to this rule is when the data map key is a Juju entity with a well-known string representation, such as a unit name or machine id.

The definition must be accompanied by a unit test, which may look as follows. Note that including a custom validator requires a comprehensive set of unit tests.

```py
DATABAG = {"foos": [
    {"foo": "a"},
    {"strange-data": "bar"},
    {"foo": "b", "new-field": "d"}
]}

def test_foos():
    accepted_foos = charm_lib.parse(DATABAG).foos
    assert accepted_foos == {"a", "b"}
```

### URLs and URIs

URLs, URIs, and URI-like connection strings are encouraged.

Each URL field must be documented and tested for consistency and precision:

- what the purpose of the URL is
- what kind of URL it is, semantically
- what components are allowed
- what values are allowed for each component

A sample checklist:

- is this a base URL, an endpoint, a full URL, an opaque identifier, or an application-specific URI or string
- limits for the URL as a whole, such as max length or allowed alphabet
- is the scheme required, optional or not allowed; what schemes are allowed
- is the userinfo required, optional or not allowed; what elements of userinfo are allowed
- is the host required, optional or not allowed; what kind of values: domain names, IPv4 addresses, and/or IPv6 addresses
- is the port required, optional or not allowed; what range of values
- is the path required, optional or not allowed; any restrictions on the path, such as max length
- is the query required, optional or not allowed; any restrictions on keys, expected treatment for duplicate keys
- is the fragment required, optional or not allowed; any restrictions, such as max length

A set of unit tests that verify the allowed URLs may look like this, at minimum:

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
def test_good_url_field_values(good_url: str):
    SomeData(url_field=good_url)
```

### Semantic grouping

The relation data should be structured to reflect the meaning of data, for example:

```py
# Do this:
{
    "direct": {"host": ..., "port": ...},
    "upstream": {"base_url": ..., "path": ...}
}

# Avoid this:
{
    "host": ...,
    "port": ...,
    "base_url": ...,
    "path": ...,
}
```

### Secret content schema

When a secret is shared over a relation, the secret content schema must be contained in the same charm library as the relation interface schema.

The same rules apply to the secret content:

- no mandatory fields
- no field reuse
- allowed URL or URI components

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
    assert charm_lib.get_secret_thing() == "foo"

def test_bad_secret():
    monkeypatch.setattr("charm_lib._load_secret", BAD_SECRET_CONTENT)
    charm_lib.parse(DATABAG)
    with pytest.raises(SomeCharmLibError):
        charm_lib.get_secret_thing()
```
