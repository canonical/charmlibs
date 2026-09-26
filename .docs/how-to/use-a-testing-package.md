---
myst:
  html_meta:
    description: Use an interface library's testing package to write state-transition tests for your charm, without knowing the relation's wire format.
---

(how-to-use-a-testing-package)=
# How to use a testing package in state-transition tests
% Based on: OP093 - Charm library testing API

Every `charmlibs.interfaces` library ships a companion *testing package*, which stands in for the application on the other end of the relation while you test your charm. Using it means your charm's tests never touch the relation's wire format: they arrange a relation, run your charm, and assert on what your charm did.

This guide covers what is true of every testing package. For the arguments a particular library accepts — what its simulated remote can be asked to do — see that library's own how-to guide and reference docs.

Read more: {ref}`how-to-provide-data-for-charm-tests`, for writing a testing package rather than using one.

## Install the testing package

Add the library's `testing` extra to your test dependencies:

```toml
[dependency-groups]
unit = [
    "charmlibs-interfaces-<name>[testing]",
]
```

Depend on the extra rather than on `charmlibs-interfaces-<name>-testing` directly. The two distributions pin each other exactly, and going through the extra is what keeps the version of the testing package you get matched to the version of the library your charm uses.

Then import the testing package alongside the library:

```py
from charmlibs.interfaces import my_interface, my_interface_testing
```

## The simulated remote

A testing package exposes two classes, `RemoteProvider` and `RemoteRequirer`. Each instance stands in for **one remote application** related to your charm over **one endpoint**.

The remote plays the *opposite* role to the charm under test: a requirer charm is tested with a `RemoteProvider`, and a provider charm with a `RemoteRequirer`.

An instance is immutable, and a method's result depends only on the arguments it was constructed with and the `State` it is given. Nothing accumulates between calls. So a remote can live at module level and be shared by every test in the file:

```py
CERTS = my_interface_testing.RemoteProvider("certificates")
```

The first argument is `endpoint`, your charm's endpoint name for this relation. It is required, and can be given positionally or by keyword. Every other argument is optional and keyword-only, and defaults to the happy path — a typical, valid, well-behaved remote. `endpoint` and `remote_app_name` are readable back off the instance.

Each remote has four methods:

| Method | What it does |
|---|---|
| `integrate(ctx, state, *, end=...)` | Adds the relation and carries the conversation as far as `end` |
| `publish(state)` | Writes the remote's data. Does not run your charm |
| `run_changed(ctx, state)` | Runs your charm for `relation-changed` on this relation |
| `get_relation(state)` | Returns this remote's `ops.testing.Relation` from the state |

Each of the first three takes a `State` and returns a new one, leaving the state it was given untouched. `get_relation` is the escape hatch for every relation event the others don't cover, and is also how assertions read the relation afterwards.

The happy path is one line, and it is the same line for every interface and every role:

```py
def test_the_happy_path(ctx: testing.Context, mocked: None):
    state_out = CERTS.integrate(ctx, testing.State.from_context(ctx))
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

## How far `integrate` goes

`integrate` simulates `juju integrate`: it adds the relation to the state, then runs your charm for `relation-created`, `relation-joined` and `relation-changed`. Its `end` argument then says how much of the rest of the conversation to carry:

| `end` | the relation is left with… |
|---|---|
| `"integrated"` | the relation made, and your charm having published whatever it publishes on integration |
| `"published"` | the above, plus the remote's data on the wire, not yet seen by your charm |
| `"received"` (default) | the above, plus your charm having run `relation-changed` against it |

The three values name the three **postconditions**, not the steps, because a postcondition is what a test is choosing between. A test is about a charm in a particular situation — has it asked yet, has it been answered, has it reconciled — and `end` names that situation rather than the number of moves it took to reach it.

```py
def test_blocked_while_waiting(ctx: testing.Context, mocked: None):
    state = CERTS.integrate(ctx, testing.State.from_context(ctx), end="integrated")
    state_out = ctx.run(ctx.on.update_status(), state)
    assert isinstance(state_out.unit_status, testing.BlockedStatus)
```

A relation that exists with *nothing* written on it at all is *below* `"integrated"`. That's a bare `ops.testing.Relation`, and needs nothing from a testing package — but build it from the remote's own attributes, so that the two agree and the remote can still find it later:

```py
relation = testing.Relation(
    CERTS.endpoint, interface="my-interface", remote_app_name=CERTS.remote_app_name
)
```

`integrate` adopts a bare relation that is already in the state, which is what `ops.testing.State.from_context` puts there for every endpoint in your charm's metadata. A relation that already has data on it means the conversation has begun, and raises: carrying one on is what `publish` and `run_changed` are for.

(how-to-use-a-testing-package-settled)=
## What `end="received"` does and does not settle

`end="received"` leaves the relation settled *for the conversation `integrate` ran*. It is not a promise that no further hook would change anything.

The gap opens where your charm publishes in response to what it received. `integrate` ends by running your charm against the remote's data; if that run made your charm publish something new, the remote has not answered it yet. Reaching a genuine fixed point takes another round:

```py
state = CERTS.integrate(ctx, testing.State.from_context(ctx))
state = CERTS.publish(state)            # answer whatever the last run asked for
state = CERTS.run_changed(ctx, state)   # let the charm reconcile against the answer
```

Repeat the pair until the state stops changing. There is deliberately no method that does this for you: a name for it would be a name for a composition of things that already have names, and any short name — `settle`, say — would claim more than it could deliver, since it says nothing about *what* settled.

Whether the extra round is needed is a property of the interface and of your charm, not of the testing package, and most of the time it is not. The reliable way to find out is to look: run the extra round and compare.

```py
def test_the_extra_round_is_a_no_op(ctx: testing.Context, mocked: None):
    settled = CERTS.integrate(ctx, testing.State.from_context(ctx))
    again = CERTS.run_changed(ctx, CERTS.publish(settled))
    assert CERTS.get_relation(again).local_unit_data == (
        CERTS.get_relation(settled).local_unit_data
    )
```

A test that reaches for the extra round when it isn't needed costs a little time and nothing else, since `publish` is idempotent and a redundant `relation-changed` on a settled relation changes nothing. Leaving it out when it *is* needed leaves the test asserting on a charm that hasn't finished.

## Later turns of the conversation

`publish` and `run_changed` are the two moves that drive every turn after the first — after a config change, a credential rotation, or anything else that makes your charm publish again:

```py
state = ctx.run(ctx.on.config_changed(), state)  # the charm asks for something different
state = CERTS.publish(state)                    # the remote answers the new request
state = CERTS.run_changed(ctx, state)           # the charm reconciles against the answer
```

`publish` is *recomputing*, not appending. It adds what your charm's published data now warrants, keeps what is still warranted, and removes what no longer is — an answer to a request your charm has since withdrawn, for instance, which is what the real remote's library does too. Its postcondition is "the remote's data is correct for this state", not "an answer has been appended".

Two things follow. It is idempotent: calling it twice with nothing else changed leaves the state unchanged. And it needs no separate API for later turns, because calling it again is exactly what a later turn requires.

`publish` does **not** raise merely because your charm published nothing for it to answer, or because the remote never writes on this interface at all. It writes nothing and hands the state back, so that a test which arranges a relation incidentally while being about something else isn't obstructed. A missing *relation* is a different matter: that is not an absence of data but an incoherent call, and does raise.

## The `mocked()` scope

Every testing package exposes a `mocked()` context manager, which mocks out the library's own internals for the duration of a test. Every call that builds state or runs your charm must be inside it, and raises if it isn't. `get_relation` is the exception, so that assertions can read the relation after the scope has closed.

Open it in a fixture, and keep it open for your charm's execution as well as the arrangement:

```py
@pytest.fixture()
def mocked():
    with my_interface_testing.mocked():
        yield
```

The scope is reentrant, so a fixture and the test that uses it may each open one, and several libraries' scopes stack in any order:

```py
@pytest.fixture()
def mocked():
    with (
        tls_certificates_testing.mocked(),
        certificate_transfer_testing.mocked(),
    ):
        yield
```

A test that needs a library mocked but has no interest in the relation can depend on the fixture alone.

The scope is required even where the library mocks nothing today, and would be required even if it never mocked anything. A library that didn't require it would break every test written against it on the day it started mocking something. Requiring it from the start makes any future change to `mocked()` a non-breaking one.

## Shared limitations

**One remote unit.** The simulated remote application has exactly one unit, with unit ID 0. `integrate` fires `relation-joined` and `relation-changed` once, for that unit, and `publish` writes the remote application's databag and unit 0's. An interface that aggregates across the *units* of one remote application can't be fully exercised. Aggregating across several remote *applications* on one endpoint can be, with one remote per application and a distinct `remote_app_name` each — where the library supports it; one that doesn't raises `ValueError` rather than silently replacing the first remote.

**No scale events.** A unit joining or departing partway through a test isn't expressible through these methods. `get_relation` plus an explicit `ctx.run` is the answer for now, and the same goes for `relation-departed` and `relation-broken`:

```py
def test_relation_broken(ctx: testing.Context, mocked: None):
    state = CERTS.integrate(ctx, testing.State.from_context(ctx))
    state_out = ctx.run(ctx.on.relation_broken(CERTS.get_relation(state)), state)
    assert isinstance(state_out.unit_status, testing.BlockedStatus)
```

## The `ops.testing.Context`

`integrate` and `run_changed` run your charm, which mutates `ctx`: `ctx.run` appends to `ctx.emitted_events` and the other accumulating attributes. Don't assume how many times `integrate` runs your charm, or that a future version will run it the same number of times. `run_changed` is the exception — its equivalence to a single `ctx.run` for `relation-changed` is part of its specification.

An exception raised while your charm is executing propagates to you. A charm that errors during `integrate` or `run_changed` — because it is broken, because state it needs hasn't been set up, or because another library it uses hasn't been mocked — fails the test, and the testing package won't catch or annotate it.
