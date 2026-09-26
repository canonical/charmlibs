(how-to-provide-data-for-charm-tests)=
# How to provide relation data for charm tests

This guide describes how charm interface libraries should provide relation data for charm unit tests.
By providing test data, charm libraries prevent charms from needing to know about the underlying relation data format.
Instead, charms only need to know about the library's public API and its testing API.

As the author of an interface library, you should provide a separate testing package for your library.
The testing package should expose a pair of classes that stand in for the application on the other end of the relation, executing the charm under test to build up the `ops.testing.State` that a state-transition test needs.

`just init --interface` scaffolds all of this for you: the package, its metadata, the two classes with the generic methods already written, the `mocked` context manager, and a test suite covering the parts of the contract that don't depend on your interface.
Most of the work described below is filling in one method, `publish`, and the tests that go with it.

Read more: {ref}`how-to-use-a-testing-package`, for using a testing package rather than writing one.

## Create a separate testing package

Your library's testing package should be distributed separately from runtime library code.
The package should be defined in a `testing` subdirectory, like this:

```
interfaces/<name>/
├── src/charmlibs/interfaces/<name>/
│   └── __init__.py
├── pyproject.toml
└── testing/
    ├── src/charmlibs/interfaces/<name>_testing/
    │   └── __init__.py
    └── pyproject.toml
```

Use these naming conventions:

- Distribution package: `charmlibs-interfaces-<hyphenated-interface-name>-testing`
- Import package: `charmlibs.interfaces.<underscored_interface_name>_testing`

## Expose a testing extra and link the package versions

Keep the library and testing package versions identical.
Releasing either one always implies releasing the other.
Also, the library and its testing package should depend on exact versions of each other.

Assuming an interface library is currently on version 1.2.3, the dependencies in the library's `pyproject.toml` file should look like this:

```toml
[project.optional-dependencies]
testing = ["charmlibs-interfaces-<name>-testing==1.2.3"]

[tool.uv.sources]
charmlibs-interfaces-my-interface-testing = { path = "testing", editable = true }

[dependency-groups]
unit = [
    # If the library's unit tests use the testing package:
    "charmlibs-interfaces-<name>[testing]",
]
```

The dependencies in `testing/pyproject.toml` file should then look like this:

```toml
[project]
dependencies = [
    "charmlibs-interfaces-<name>==1.2.3",
]

[tool.uv.sources]
charmlibs-interfaces-my-interface = { path = "..", editable = true }
```


## Implement the required testing API

Your testing package must export two classes and one function:

```py
class RemoteProvider:  # and RemoteRequirer
    def __init__(self, endpoint: str, *, remote_app_name: str = "remote", ...) -> None: ...
    @property
    def endpoint(self) -> str: ...
    @property
    def remote_app_name(self) -> str: ...
    def __repr__(self) -> str: ...
    def integrate(
        self,
        ctx: ops.testing.Context,
        state: ops.testing.State,
        *,
        end: Literal["integrated", "published", "received"] = "received",
    ) -> ops.testing.State: ...
    def publish(self, state: ops.testing.State) -> ops.testing.State: ...
    def run_changed(
        self, ctx: ops.testing.Context, state: ops.testing.State
    ) -> ops.testing.State: ...
    def get_relation(self, state: ops.testing.State) -> ops.testing.Relation: ...


def mocked() -> contextlib.AbstractContextManager[None]: ...
```

Of the four methods, only `publish` needs to know your interface.
`integrate`, `run_changed` and `get_relation` are generic plumbing that every testing package implements the same way, and the scaffolding writes them for you, in a private `_Remote` base class that the two public classes inherit from.

Read more: {ref}`how-to-use-a-testing-package`, which documents these classes from the charm author's side and is worth reading before implementing them.

### Name the classes for the role the *testing library* plays

`RemoteProvider` stands in for a provider charm, so the charm under test is the **requirer**, and likewise `RemoteRequirer` stands in for a requirer charm and is used to test a **provider**.

```{important}
This is the opposite of the older `relation_for_<role>` functions that these classes replace, where the role named was the role of the *caller*.
A test that asked the old API for a provider's relation wants a `RemoteRequirer`, and vice versa.
This is the single most likely thing to go wrong when migrating an existing testing package, and it goes wrong quietly, because both roles exist and both produce a relation.
```

### Construct from an endpoint and nothing else

`endpoint`, the charm's endpoint name for this relation, must be required, and must be accepted positionally or by keyword.
Every other constructor argument must be optional and keyword-only, and each must default to the happy-path behaviour of a well-behaved application on the other end of the relation.
A test that wants an ordinary, valid relation should not have to say so.

Add whatever optional arguments your interface needs to let a test ask the remote for something other than the happy path — malformed data, a missing field, an unsupported version.

### Make instances immutable

An instance's constructor arguments must not be changeable afterwards, and a method's result must depend only on those arguments and the `State` it is passed.
Nothing may accumulate across calls that changes what a later call does.
Caching a derived value — a generated certificate authority, say — is fine, as long as the cache isn't observable in the results.

Together these let a charm author construct a remote once, at module level, and share it across every test in the file.

`endpoint` and `remote_app_name` must be readable as attributes.
This matters where a test builds a bare `ops.testing.Relation` itself, which is how a relation with nothing written on it at all is expressed: the relation the test builds has to agree with the remote that will later operate on it, and reading those two values off the remote is how it agrees without duplicating literals.

Give instances a useful `__repr__` too.
`pytest` derives parametrize IDs from it, and it identifies which remote raised an error when a test has several in play.

A frozen dataclass satisfies all of this, and matches `ops.testing.State` and `Relation`, which are frozen dataclasses themselves.
The specification is of the properties, though, not of the mechanism.
The scaffolding and the `tls-certificates` testing package both use plain classes with read-only properties instead, because a dataclass in public API commits you to `dataclasses.replace`, `astuple`, `asdict`, `is_dataclass` and `__dataclass_fields__` as part of your contract, which makes even adding an optional argument or reordering existing ones a breaking change.

### Require the `mocked` scope

`integrate`, `publish` and `run_changed` must raise if called outside an active `mocked()` scope.
`get_relation` must not require it, because assertions read the relation after the scope has closed, and because it is the escape hatch for relation events the other methods don't cover.

### Treat `end` as three postconditions

`integrate` simulates `juju integrate`: it adds the relation to the state, executes the charm for `relation-created`, then `relation-joined` and `relation-changed` for the remote's single unit, and then goes as far as `end` says.

| `end` | the relation is left with… |
|---|---|
| `"integrated"` | the relation made, and the charm having published whatever it publishes on integration |
| `"published"` | the above, plus the remote's data on the wire, not yet seen by the charm |
| `"received"` (default) | the above, plus the charm having been executed with `relation-changed` against it |

The three values name postconditions, not steps.
That is what a test is actually choosing between: a charm that has asked and not been answered, a charm that has been answered and not reconciled, or a settled relation.
Naming the situation rather than the number of moves needed to reach it also means the values keep their meaning for a role where a step doesn't apply.

`integrate` must raise if this remote already has a relation with data on it, since the conversation has then already begun.
An empty relation must be adopted rather than duplicated: `ops.testing.State.from_context` creates one for every endpoint in the charm's metadata, so this is the common case, not an edge case.

### Make `publish` recompute

`publish` writes the simulated remote's relation data, and any other state the remote is responsible for, such as `Secret` objects it owns or grants.
It does not execute the charm.

It recomputes that data from the current state rather than appending to it.
It adds what the charm's published data now warrants, retains what is still warranted, and **removes what is no longer warranted** — an answer to a request the charm has since withdrawn, for instance, which is what the real remote charm's library does.
Its postcondition is "the remote's data is correct for this state", not "an answer has been appended".

Two things follow.
`publish` is idempotent, so calling it twice with nothing else changed leaves the state unchanged.
And it needs no separate API for later turns of the conversation: after a config change or a key rotation, calling it again drops the stale data and writes what the new situation warrants.

### Don't raise on an absence of data

`publish` must not raise merely because the charm published nothing to answer, or because the remote never writes on this interface at all.
Write nothing and return the state unchanged.

This is deliberate in both directions.
A test that arranges this relation incidentally, while being about something else, must not be obstructed; and a charm that legitimately requests nothing still produces an output state worth asserting on.
It also keeps the call forward-compatible: if the interface later grows a response where its remote previously wrote nothing, tests that already call `publish` pick that up, whereas tests written around an error would silently keep testing less.

A **missing relation** is a different matter.
That is not an absence of data but an incoherent call, and must raise.
Distinguish likewise between what your interface *cannot express* — a capability the library does not have, which must raise `ValueError` — and what the remote simply *would not do* in this state, which is a no-op.

Where you can identify a specific, unambiguous reason that the charm published nothing, you *should* raise and say so.
The canonical case is a library that writes to the application databag being used with a non-leader state, which yields an empty relation for a reason that is invisible in the resulting state and easily mistaken for a bug in the charm.
Judge that case for your own interface: the `tls-certificates` testing package logs a warning rather than raising, having judged non-leadership specific but not unambiguous, since a `Mode.UNIT` requirer publishes as a non-leader perfectly well and a charm with no requests configured also publishes nothing.

### Derive the response, never can it

Where the charm under test writes before the remote does, the remote's data **must** be derived from what the charm actually published.
Read it off `relation.local_app_data` and `relation.local_unit_data`; don't write a fixed value supplied by your package or by the test author.

This is the whole point of the design.
A testing package that ignores the charm's relation data and writes canned values satisfies every other rule here while reintroducing exactly the silent mismatches it exists to prevent: relation data that the charm's own library will delete and rewrite on its next reconcile, or that the charm will accept as an answer to a question it never asked.

`publish` taking no `ctx` does not enforce this on its own.
It stops your package obtaining anything the charm has not already published, but you could still ignore the state and write canned data — so this is a rule to follow, and the one below is the test that checks it.

Where the remote writes first, and the charm reads before it writes, there is nothing to derive from, and the remote's data is supplied by your package as usual.

### Write the conformance test

Every testing package must include a test that the response is derived rather than canned: run two charms that ask for **different** things, and assert that the simulated remote's data differs accordingly — not merely that it is non-empty.

This is the only part of the contract that can't be checked by reading a signature, and it is the part that the whole design depends on, so it is worth the one test per package that it costs.
For a role where the remote writes first there is nothing to derive, and the test does not apply.

`just init --interface` scaffolds this test as a skipped placeholder with instructions, in `testing/tests/unit/test_testing.py`.
A worked example is `test_provider_derives_its_answer_from_what_the_charm_published` in `interfaces/tls-certificates/testing/tests/unit/test_testing.py`.

### One remote per application, one unit per remote

An instance stands in for one remote application related to the charm over one endpoint, identified by `endpoint` **and** `remote_app_name`.

Supporting several remotes on one endpoint is optional, so that libraries which aggregate over multiple remote applications can be tested.
A library that does not support it must raise `ValueError` rather than silently replacing the first remote.

Whichever you support, relation data and other library-managed state belonging to *this* remote may be removed or replaced, but state belonging to other remotes on the same endpoint must be preserved, and so must the rest of the state — other relations, other endpoints, containers, config.

The simulated remote application has exactly one unit, with unit ID 0.
`integrate` fires `relation-joined` and `relation-changed` once, for that unit, and `publish` writes the remote's application databag and unit 0's databag.
Scale events — a unit joining or departing partway through a test — are out of scope for this revision, and `get_relation` plus an explicit `ctx.run` is the answer for them, as it is for `relation-departed` and `relation-broken`.

### Define `mocked`, even if it does nothing

`mocked()` mocks out your library's own internals for the duration of a test.
Some libraries need this — anything that manages Kubernetes resources outside the Juju model, for instance — and some have nothing to mock.

The requirements are the same either way:

- It must be callable with no arguments. Optional keyword-only arguments are allowed; required ones are not.
- Only your own library's internals may be mocked. Nothing defined outside the library, so that charm code which doesn't pass through your library has no side effects.
- It must be [reentrant](https://docs.python.org/3/library/contextlib.html#reentrant-context-managers), so that a fixture and the test that uses it may each open a scope, and so that several libraries' scopes nest in any order.
- **Every** library must define it, including one that currently mocks nothing, in which case it is a no-op. A library that didn't define and require it would break every test written against it on the day it started mocking something; requiring it from the start makes introducing mocking a non-breaking change.
- The scope must stay open for as long as the charm is executed, which includes the test's own act step and not only its arrangement.

Mocking can change what a charm's unit tests see, so let your library's version reflect that: substantial changes to mocking warrant a minor version bump rather than a patch bump, and truly breaking changes to testing should be avoided within a major version of the library.

The specification is of a context manager, not of a generator decorated with `@contextlib.contextmanager`; either implementation is fine.


## Test the testing package

The testing package should have its own test suites like any other package.
It should only have unit tests, since the package itself only targets use in unit tests.

`just init --interface` scaffolds tests covering the parts of the contract that don't depend on your interface: that the state-producing methods raise outside a `mocked` scope, that `integrate` honours each value of `end`, that the methods preserve the rest of the state, and that `run_changed` is equivalent to a single `ctx.run`.
It also scaffolds skipped placeholders for the tests only you can write — that `publish` is idempotent, that it removes what is no longer warranted, and the conformance test above.

In the `charmlibs` monorepo, the testing package's tests are run automatically in CI whenever the interface package or its testing package are changed.
You can run the tests locally like this:

```
just unit interfaces/<interface name>/testing
```


## Example usage in charm tests

Charms should specify the version of the library that they need in their dependencies.
In their testing dependencies, they should require the library's `testing` extra, but not specify any version constraints.

A charm author constructs a remote for the role opposite their charm's, opens your `mocked` scope, and arranges the relation in one line:

```python
from charmlibs.interfaces import my_interface_testing

# The charm under test is the requirer, so the remote is the provider.
REMOTE = my_interface_testing.RemoteProvider("my-endpoint")


def test_the_happy_path(ctx: testing.Context):
    with my_interface_testing.mocked():
        state_out = REMOTE.integrate(ctx, testing.State.from_context(ctx))
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

Later turns of the conversation are `publish` and `run_changed`, which is why they are separate methods rather than only steps inside `integrate`:

```python
def test_a_later_turn(ctx: testing.Context, happy_state: testing.State):
    with my_interface_testing.mocked():
        state = ctx.run(ctx.on.config_changed(), happy_state)  # the charm asks for something else
        state = REMOTE.publish(state)                          # the remote answers the new request
        state_out = REMOTE.run_changed(ctx, state)             # the charm reconciles against it
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

```{tip}
Charms should always depend on `charmlibs-interfaces-<name>[testing]`, not directly on `charmlibs-interfaces-<name>-testing`.
This ensures that the testing package version always matches the library itself.
```

Read more: {ref}`how-to-use-a-testing-package`, which is the charm author's side of everything above.
