(design-relation-interfaces)=
# How to design your charm library API
% Based on: OP083 - Relation Interface Design

To allow interface evolution, the charm-facing API should be decoupled from the interface parsing code. The Python code in the charm library typically deals with:

- logic: combining fields, filtering values
- stable Python API: both new and legacy interface fields are processed
- run-time: wrapping and suppressing errors in further dependencies and secrets
- arguments: charm context, for example the arguments that charm passes to the library
- third-party dependencies, for example loading PEM content in `cryptography.x509` primitives

Adopt the following conventions in charm libraries that wrap interfaces.

## Design the library API

### Handle bad remote data

Initialising the charm library object, and superficial API access (`.is_ready`, detailed status: see below) must not raise exceptions due to relation data.
Most importantly parsing the remote data must not lead to a charm-level exception / unit going into the error state.

- charm object initialisation must not raise
- charm object `.is_ready` must not raise

Relation data should not be loaded at charm object initialisation time, but if it is, the library should catch exceptions arising from `ops.Relation.load()`.
Likewise, `.is_ready` should catch exceptions arising from loading and parsing the data.

Exceptions can and should be used to report incorrect initialization (wrong relation name), or transient errors (unexpected hook command errors).

Unit tests must be used to validate that initialisation and ready markers don't crash the charm on bad data:

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

The charm library must provide an API that quickly determines if the endpoint is "ready" for a particular purpose.
Accessing `is_ready` must be free from side effects, must not raise exceptions and the return value must be `False` in these cases:

- the relevant relation data is empty, when appropriate
- the relevant relation data could not be parsed
- the library evaluated the data and determines that it's logically "not ready"

The specific shape of the API varies, here are some common examples:

- `.is_ready` property in a simple requirer
- `.is_ready(self, relation: ops.Relation)` method in an application provider
- `.is_ready(self, relation, remote_unit)` method in a per-unit provider
- `.is_foo_ready` and `.is_bar_ready` when the interface provides two functions
- `.is_request_ready` and `.is_acknowledgement_ready` when two distinct states can be expressed over the interface

A set of unit tests must be provided that clearly shows what data is considered "ready":

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

A unit tests must be provided that shows how the interface error is surfaced:

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
