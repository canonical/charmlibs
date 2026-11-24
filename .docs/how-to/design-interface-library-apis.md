---
myst:
  html_meta:
    description: Design the charm-facing API of an interface library for charms that reconcile, as a plain accessor over relation data with no events of its own.
---

(design-interface-library-apis)=
# How to design an interface library API
% Based on: OP083 - Relation Interface Design

An interface library should give charms a plain object that reads and writes relation data only when the charm calls it, and that works in the charm's own types rather than the relation data format.
A charm that reconciles calls it from its reconcile handler, and a charm that handles events separately calls it after the events that it lists.
Whatever a remote application sends, constructing the library object and checking whether it's ready must never raise, and once it's ready, its getters shouldn't raise either.

This guide provides rules for the charm-facing API. For the relation data format, see {ref}`design-relation-interfaces`.

```{note}
These rules apply to new interface libraries, and to new major versions of existing ones.
A library that doesn't follow them isn't broken, and doesn't need to be rewritten.
```

## The approach, and why

1. **Write a plain class for each side of the relation, constructed from `ops.Model`, that doesn't emit or observe events.**

   Reconciling is the most reliable way to write a charm.
   A Juju event tells the charm that something changed, but not what, so even a charm that handles each event separately ends up recomputing its state.
   A reconciling charm does that directly: it observes the events it cares about with a single handler, reads all the state it needs, and writes everything that should change.

   An interface library should fit into that handler, and a library that observes events and emits its own works against it.
   The charm has to observe custom events that only say "something changed", or copy relation data elsewhere so that it can use the data outside those events.
   Some libraries also take a `refresh_event` argument: a list of the charm's own events, such as `config-changed`, that the library observes as well, so that it can publish again when something that the charm owns changes.
   The timing of the library's work is then split between the library and the charm, and deferred custom events add more paths again.
   A library that reads and writes only when it's called has none of these problems.

2. **Start with the smallest API that lets charms do their job.**

   Every public method is one that charms might come to depend on, and removing one is a major release.

3. **Give charms their own types, and keep the relation data format private.**

   The relation data format has to stay compatible with every version of the library on the other side of the relation, and carries details that only the library needs.
   If charms use it directly, every change to the format is a change to every charm.

4. **Provide a readiness check, getters named after the data that the charm uses, and methods that publish data when they're called.**

   These are what a reconciling charm calls from its handler.
   Charm authors use many interface libraries, so when the libraries agree on this shape and its names, learning one teaches the next.

5. **Make sure that bad remote data can't put the charm into an error state, and ship tests that show it.**

   A charm's `__init__` must complete for the charm to handle any event, and a complex charm constructs many library objects there.
   A library can't know whether it's critical to a particular charm, so malformed data from a remote application must never stop the charm from handling events.
   The charm checks readiness first, and once the library is ready, the getters shouldn't raise.

6. **Provide an `events` method, so that charms that handle each event separately can use the library too.**

   Not every charm reconciles yet.
   The method tells such a charm when to call the library, without rewriting the charm.

Read more: {ref}`Ops | Holistic vs delta charms <ops:holistic-vs-delta-charms>`

## The example interface

The examples on this page implement a `foo` interface.
A provider publishes the servers where it serves its API, and creates a tenant in its workload for each requirer.
A requirer connects to one of the servers, as its tenant.

The requirer provides `is_ready()`, `get_server()`, `get_tenant()`, and `rich_status()`.
The provider provides `publish()`, `get_outstanding_requests()`, `publish_tenants()`, and `get_unused_tenants()`.
Both sides provide `events()`.

## General requirements

### Write a plain class

Don't subclass `ops.Object`.
It exists so that objects can emit and observe events and use `ops.StoredState`, none of which an interface library needs.
Being an `ops.Object` also means that the charm has to pass itself to the library as the parent object, which gives the library the whole charm, and that constructing a second object with the same key, typically the relation name, raises an error.

Take `ops.Model` as the first argument.
It provides everything that an interface library needs: relations, the local application and unit, and Juju secrets.

```py
_DEFAULT_RELATION_NAME = 'foo'


class FooRequirer:
    """Requirer side of the foo interface.

    The charm must declare the endpoint with ``limit: 1``.
    """

    def __init__(self, model: ops.Model, relation_name: str = _DEFAULT_RELATION_NAME) -> None:
        if relation_name not in model.relations:
            raise ValueError(f'{relation_name!r} is not a relation endpoint of this charm')
        self._model = model
        self._relation_name = relation_name
```

In the charm:

```py
self.foo = FooRequirer(self.model)
```

Checking the relation name in the constructor is correct, even though it raises.
An undeclared endpoint is a mistake in the charm, not a problem with relation data, and it would fail in every hook.

Raise a built-in exception, such as `ValueError`, for a mistake in the charm, because the charm shouldn't catch it.
Define your own exception types, such as `FooNotReadyError`, only for conditions that a charm is expected to handle.

Use constructor arguments only to configure how the library behaves.
A setting is fine as long as each method means the same thing whatever its value, such as a scope that decides which databag the library writes to.
If a method's docstring has to explain how the method behaves differently depending on a constructor argument, use two objects, or move the choice to a method argument.

If you need a value from the charm, take the value rather than the charm.
For example, take `is_subordinate: bool` rather than the charm object to read `charm.meta.subordinate`.
Don't take data to publish, events, or callbacks in the constructor.

(interface-library-reconcile)=
### Leave events to the charm

The library shouldn't define custom events, call `framework.observe`, or accept `refresh_event` arguments or callbacks.
The charm observes Juju events, and calls the library from its own handlers.

A reconciling charm calls the library from its reconcile handler, which it observes for every event it cares about, including the relation events for the library's endpoint:

```py
class ReconcilingCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        self.reconcile_events = [
            self.on.config_changed,
            self.on['foo'].relation_changed,
            self.on['foo'].relation_broken,
        ]
        for event in self.reconcile_events:
            framework.observe(event, self._reconcile)

    def _reconcile(self, _: ops.EventBase):
        if not self.foo.is_ready():
            self.unit.status = ops.WaitingStatus(f'foo not ready: {self.foo.rich_status()}')
            return
        server = self.foo.get_server()
        tenant = self.foo.get_tenant()
        ...
```

Every method that the charm calls should be safe to call from any event, as often as the charm likes.
The rest of this guide shows how.

(interface-library-smallest-api)=
### Start with the smallest API

Provide the methods that charms need to do their job, and no more.
The methods listed for the `foo` interface are all that its charms need.

It's tempting to also expose the data underneath, such as every server that the provider offers, or which requirer has which tenant.
Wait until a charm needs it.
Adding a method later is a minor release, but removing one is a major release, and every public method is one that charms might come to depend on, instead of the one that you intended them to use.

When you do add a lower-level method, return the same charm-facing types, so that it's another view of the same data, rather than a second API.
Never expose the relation data format, even as a lower-level option.

### Require a recent `ops`

Read and write relation data with `ops.Relation.load` and `ops.Relation.save`, and require `ops>=3.8.1,<4`.
Before `ops` 3.8.1, `load` JSON-decoded every key in the databag, not just the fields of your data model.
That fails on any key that isn't JSON, including `ingress-address`, which Juju sets in every unit databag.

If the library must also support charms that are still on `ops` 2, the fix is in `ops` 2.23.6 too, but not in 3.0 to 3.8.0, so exclude those:

```text
ops>=2.23.6,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*,!=3.5.*,!=3.6.*,!=3.7.*,!=3.8.0,<4
```

Everything on this page works with both ranges.

Read more: {ref}`python-package-deps`

(interface-library-private-format)=
## Keep the relation data format private

The data model that you load and save describes the relation data format.
It has to follow the rules in {ref}`design-relation-interfaces`: every field is optional, collections are sets in a stable order, and old fields can't be reused.
It also carries details that only the library needs, such as request IDs, or the IDs of Juju secrets.
None of that is the charm's concern.

Keep the data model private, and give charms their own types that describe what they use.
Don't return the data model from a getter, or take it as an argument to `publish`.

### Give charms their own types

Write a plain class with read-only properties:

```py
_PROTOCOLS: Final = ('grpc', 'http')  # in order of preference


class FooServer:
    """A server where a foo provider serves its API."""

    def __init__(self, *, url: str, protocol: Literal['grpc', 'http'] = 'http') -> None:
        if not url:
            raise ValueError('url must not be empty')
        if protocol not in _PROTOCOLS:
            raise ValueError(f'protocol must be one of {_PROTOCOLS}, not {protocol!r}')
        self._url = url
        self._protocol: Literal['grpc', 'http'] = protocol

    @property
    def url(self) -> str:
        return self._url

    @property
    def protocol(self) -> Literal['grpc', 'http']:
        return self._protocol

    ...  # __eq__ and __hash__, comparing url and protocol, and __repr__
```

Follow these rules for charm-facing types:

- **Make properties read-only.** The library doesn't write these objects back to the databag, so changing one would do nothing.
- **Take keyword-only constructor arguments**, so that you can add new ones with defaults later.
- **Decide on equality from the start.** If charms compare values or collect them in sets, define `__eq__` and `__hash__` together. Adding `__eq__` later, without `__hash__`, makes the class unhashable.
- **Validate in the constructor**, and raise `ValueError`, so that an invalid value can't exist. Check at runtime even what the type annotations say, because not every charm runs a type checker. The {ref}`conversion <interface-library-convert>` relies on these checks too.
- **Be stricter than the relation data format.** `url` is required here, even though it's optional on the wire, because the library never returns a server without one.
- **Use `Literal` for a fixed set of values**, such as `protocol`. Type checkers then catch a typo in the charm, and the annotation documents what a charm can get back. Adding a value later changes the property's type, but returning a value that existing charms don't handle would break them anyway.

```{admonition} Why not a dataclass?
:class: tip

A dataclass commits you to `dataclasses.fields()`, `asdict()`, `astuple()`, and `replace()` working, with the same results, for the rest of the major version, because charms can call them on any value that the library returns.
A named tuple commits you to indexing and unpacking in the same way, and a pydantic model to `model_dump()` and the rest of the pydantic API.
Charms come to rely on whatever is there, so a plain class keeps the API to what you designed.
```

(interface-library-convert)=
### Convert in one place

Keep the data model and the conversion private:

```py
class _Server(pydantic.BaseModel, frozen=True):
    url: str | None = None
    protocol: str | None = None


class _ServerData(pydantic.BaseModel):
    servers: frozenset[_Server] | None = None

    @pydantic.field_serializer('servers')
    def _sorted(self, servers: frozenset[_Server] | None) -> list[_Server] | None:
        if servers is None:
            return None
        return sorted(servers, key=lambda s: (s.url or '', s.protocol or ''))


class _TenantData(pydantic.BaseModel):
    tenant: str | None = None


class _ProviderAppData(_ServerData, _TenantData):
    """The provider's application databag, which the requirer reads."""


def _to_wire(servers: Iterable[FooServer]) -> _ServerData:
    wire = frozenset(_Server(url=s.url, protocol=s.protocol) for s in servers)
    return _ServerData(servers=wire)


def _from_wire(data: _ServerData) -> frozenset[FooServer]:
    servers: set[FooServer] = set()
    for s in data.servers or ():
        protocol = cast("Literal['grpc', 'http']", s.protocol or 'http')  # FooServer checks it
        try:
            servers.add(FooServer(url=s.url or '', protocol=protocol))
        except ValueError as e:
            logger.debug('Skipping a server that this version cannot use: %s', e)
    return frozenset(servers)
```

The provider publishes servers and tenants separately, so each has its own model, and `_ProviderAppData` combines them for reading. See {ref}`interface-library-publish`.

The conversion is the one place that knows about the relation data format, so it's where to:

- **Read and write older formats.** When the format changes, both versions convert to the same charm-facing type, and charms don't change. While older versions of the library might be on the other side of the relation, `_to_wire` can write the old format alongside the new one.
- **Interpret missing values.** Here, a missing protocol means HTTP.
- **Skip what this version can't use**, such as a protocol added in a later version of the interface, without rejecting the rest. Construct each item with the charm-facing type, and skip it if the constructor raises `ValueError`. Then the constructor is the one definition of what the library can use, and the conversion can't fall out of step with it.
- **Add and remove details that only the library needs**, such as request IDs, or the ID of a Juju secret. If the library shares data through a secret, give the charm the secret's content, not its ID.
- **Sort collections.** Pydantic serialises a set in an order that varies between processes, so without sorting, the same data produces a different databag and wakes up the remote application with `relation-changed`.

The testing package should take charm-facing values too, such as `relation_for_requirer('foo', servers=[...])`, and use the private conversion to build the relation data.
Because the testing package depends on an exact version of the library, it can use private names.

Read more: {ref}`how-to-provide-data-for-charm-tests`

## Read relation data

### Provide a readiness check

The library must provide a quick way for the charm to check whether the endpoint is ready to use.
The readiness check must:

- not raise because of relation data
- have no side effects
- return `False` when the data is missing, can't be parsed, or isn't usable

```py
class _Ready(NamedTuple):
    servers: frozenset[FooServer]
    tenant: str


class FooRequirer:
    ...

    def is_ready(self) -> bool:
        """Whether there's a usable server and a tenant. Never raises."""
        ready, _ = self._load()
        return ready is not None

    def _load(self) -> tuple[_Ready, None] | tuple[None, str]:
        """The data that the requirer uses, or why the endpoint isn't ready."""
        relations = self._model.relations.get(self._relation_name, ())
        if not relations:
            return None, f'no {self._relation_name} relation'
        if len(relations) > 1:
            return None, f'{len(relations)} {self._relation_name} relations, expected one'
        relation = relations[0]
        if not relation.data[relation.app]:
            return None, f'waiting for {self._relation_name} data'
        try:
            data = relation.load(_ProviderAppData, relation.app)
        except ValueError as e:
            logger.warning('Invalid %s data: %s', self._relation_name, e)
            return None, f'invalid {self._relation_name} data'
        servers = _from_wire(data)
        if not servers:
            return None, 'no usable servers'
        if not data.tenant:
            return None, 'waiting for a tenant'
        return _Ready(servers, data.tenant), None
```

`_load` returns a pair: the data that the requirer uses, or the reason that the endpoint isn't ready.
The data is converted, rather than `_ProviderAppData`, whose fields are all optional, so that the getters don't have to check again what `_load` has checked.
The readiness check, the getters, and the {ref}`status API <interface-library-status>` all share it.

Some details to get right:

- Check for an empty databag before parsing. Because the data model has no mandatory fields, an empty databag parses successfully.
- Count the relations yourself. `model.get_relation()` raises `ops.TooManyRelatedAppsError` if a second application is related, and a library can't enforce `limit: 1`.
- If readiness depends on a Juju secret, read it with `Secret.peek_content()`, which doesn't change the revision that the charm tracks, and return `False` on `ops.ModelError`. That covers `ops.SecretNotFoundError`, a subclass, for a secret that's gone. It also covers a grant that hasn't reached this unit yet: Juju answers "permission denied", which `ops` raises as a plain `ModelError`, and at the API, a grant that's late can't be told apart from one that will never come. Catch `ModelError` only around secret reads.
- Don't cache what you load. `ops` reads each databag once per hook and keeps the result, including what the charm writes during the hook, so loading again costs a JSON decode and a validation, not a hook command. A cache of your own would go stale when the library writes to a databag that it also reads, as the provider does with tenants. `ops.Model.get_secret()` isn't cached, though: each call runs a hook command.

Make readiness a method, not a property, even when it takes no arguments, as `is_ready()` does here.
It does work each time it's called, it can take arguments in a later version without breaking charms, and charms then call every library's readiness check the same way.
A provider with many relations can use `is_ready(relation)`, and a library that makes several independent requests can use `is_ready(request)`.
An endpoint whose data is useful for different purposes at different times can provide one method per purpose, such as `is_upstream_ready()`.
For a provider that answers requests, {ref}`the outstanding requests <interface-library-requests>` do the job of a readiness check.

Test readiness with good data:

```py
META = {'name': 'consumer', 'requires': {'foo': {'interface': 'foo', 'limit': 1}}}


class RequirerCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)


def test_is_ready_with_good_data():
    ctx = testing.Context(RequirerCharm, meta=META)
    servers = [
        {'url': 'http://foo.example:4318'},
        {'url': 'grpc://foo.example:4317', 'protocol': 'grpc', 'new-field': 'x'},
    ]
    data = {'servers': json.dumps(servers), 'tenant': '"tenant-1"'}
    relation = testing.Relation('foo', remote_app_data=data)
    with ctx(ctx.on.relation_changed(relation), testing.State(relations={relation})) as mgr:
        assert mgr.charm.foo.is_ready()
        assert mgr.charm.foo.get_server() == FooServer(
            url='grpc://foo.example:4317', protocol='grpc'
        )
        assert mgr.charm.foo.get_tenant() == 'tenant-1'
```

### Read data with getters

Name each getter after the data that the charm uses.
The getters share a thin wrapper around `_load` that raises when the endpoint isn't ready:

```py
class FooNotReadyError(Exception):
    """Raised by FooRequirer's getters when the endpoint isn't ready."""


class FooRequirer:
    ...

    def get_server(self) -> FooServer:
        """The server to use: the most preferred protocol, then the first URL.

        Raises:
            FooNotReadyError: if the endpoint isn't ready. Check ``is_ready()`` first.
        """
        servers = self._load_or_raise().servers
        return min(servers, key=lambda s: (_PROTOCOLS.index(s.protocol), s.url))

    def get_tenant(self) -> str:
        """The tenant that the provider created for this application.

        Raises:
            FooNotReadyError: if the endpoint isn't ready. Check ``is_ready()`` first.
        """
        return self._load_or_raise().tenant

    def _load_or_raise(self) -> _Ready:
        ready, problem = self._load()
        if ready is None:
            raise FooNotReadyError(problem)
        return ready
```

- **A getter that returns one value raises** when there's no value to return. The charm checks readiness first, and gets a value that it doesn't need to check for `None`.
- **A getter that returns a collection returns it empty** when there's nothing usable.
- **Make choices for the charm.** If the provider offers alternatives, as here, return the one to use, so that every charm doesn't implement the same choice.

The readiness check and the getters do different jobs.
The readiness check is safe to call anywhere, including in the charm's `__init__`.
The getters return data that the charm can use directly.

If the endpoint combines data from several relations, such as a set of trusted CA certificates, return the combined collection.
A relation with unusable data should contribute nothing, so that one bad remote application can't affect data from the others.

Choose the arguments of the getters to match the endpoint:

| Endpoint | Readiness | Getter |
| --- | --- | --- |
| Requirer with `limit: 1` | `is_ready()` | `get_<thing>()` |
| Requirer that combines data from many relations | `is_ready()` | `get_<thing>()`, returning the combined data |
| Provider that reads data from each requirer | `is_ready(relation)` | `get_<thing>(relation)` |

Never silently pick one relation out of several.

(interface-library-status)=
### Report why the endpoint isn't ready

The library should provide a way to explain why the endpoint isn't ready.
A method that returns a short explanation, or `None`, is a good default:

```py
class FooRequirer:
    ...

    def rich_status(self) -> str | None:
        """Why the endpoint isn't ready, or None if it is. Never raises."""
        _, problem = self._load()
        return problem
```

The charm decides the status and the start of the message, and the library provides the explanation:

```text
Waiting(foo not ready: no usable servers)
charm  ^^^^^^^^^^^^^^
library                ^^^^^^^^^^^^^^^^^
```

Don't set the unit status from the library, and don't raise from the status API.
Write the explanations yourself, rather than passing on validation error messages, which change between pydantic versions.
If some problems need an operator to act, such as data that can't be parsed, while others resolve themselves, such as waiting for the remote application, consider also providing a boolean that tells them apart, so that the charm can choose between blocked and waiting status.

Test that the explanation reaches the status, using the `ReconcilingCharm` from {ref}`interface-library-reconcile`:

```py
def test_status_explains_what_is_missing():
    ctx = testing.Context(ReconcilingCharm, meta=META)
    servers = [{'url': 'quic://foo.example', 'protocol': 'quic'}]
    relation = testing.Relation('foo', remote_app_data={'servers': json.dumps(servers)})
    state = ctx.run(ctx.on.relation_changed(relation), testing.State(relations={relation}))
    assert isinstance(state.unit_status, ops.WaitingStatus)
    assert 'no usable servers' in state.unit_status.message
```

(interface-library-bad-data)=
### Handle bad remote data

Constructing the library object and calling the readiness check must not raise because of relation data.
A status API, if you provide one, shouldn't raise either.

- **Don't load relation data in the constructor.** Load it when a method is called.
- **Catch `ValueError` around `Relation.load`.** This covers both values that aren't valid JSON and pydantic validation errors.
- **Guard the conversion too.** Data that loads can still fail to convert, so catching `ValueError` around `Relation.load` isn't enough on its own. Don't let the error reach the charm. If the value is one item in a collection, skip it, as `_from_wire` does with servers that `FooServer` rejects, so that the rest stay usable. If the endpoint can't work without the value, return the reason from `_load`, so that the readiness check returns `False` and the status API explains why. Either way, if nothing usable is left, the charm finds out from the readiness check. If the conversion parses values with another library, such as certificates with `cryptography`, catch that library's errors in the same way.
- **Let other exceptions propagate.** A mistake in the charm, such as an undeclared relation name, should fail loudly. So should a hook command that fails unexpectedly, such as `relation-get` raising `ops.ModelError`, because Juju retries the hook. Secret reads are the exception, as described in the readiness check. Don't wrap the readiness check in `except Exception`.

A getter that returns one value may raise when the endpoint isn't ready, because the charm can check readiness first.
Once the readiness check has returned `True`, the getters shouldn't raise.
Sharing `_load` between them, as the examples do, makes sure of that.

Test that bad data doesn't raise, by checking readiness in the charm's `__init__`:

```py
class AssertNotReadyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        assert not self.foo.is_ready()


@pytest.mark.parametrize('data', [
    {},                                                                  # nothing published yet
    {'servers': 'not json'},                                             # not JSON
    {'servers': '{"url": "http://foo.example"}'},                        # not a list
    {'servers': '[{"url": 42}]'},                                        # wrong type
    {'servers': '[{"url": "quic://foo.example", "protocol": "quic"}]'},  # nothing usable
    {'servers': '[{"url": "http://foo.example"}]'},                      # no tenant yet
])
def test_bad_remote_data_does_not_raise(data: dict[str, str]):
    ctx = testing.Context(AssertNotReadyCharm, meta=META)
    relation = testing.Relation('foo', remote_app_data=data)
    ctx.run(ctx.on.relation_changed(relation), testing.State(relations={relation}))
```

## Write relation data

(interface-library-publish)=
### Publish data

Provide a method that publishes data as soon as it's called:

```py
class FooProvider:
    ...

    def publish(self, servers: Iterable[FooServer]) -> None:
        """Publish every server that this provider runs, replacing what was published before.

        Does nothing on a non-leader unit.
        """
        data = _to_wire(servers)
        if not self._model.unit.is_leader():
            return
        for relation in self._model.relations.get(self._relation_name, ()):
            relation.save(data, self._model.app)
```

Follow these rules when publishing:

- **Write when called.** Don't provide methods such as `add_server()` that change something in memory for a later call to publish. A charm that forgets the later call publishes nothing, and nothing tells it so.
- **Take the whole payload.** When what you publish is computed from what the charm passes in, as servers are, take everything that should be published, and replace what was published before. Don't provide methods such as `add_server()` and `remove_server()`, even ones that write straight away. With those, the charm has to work out what changed since it last published, and a missed call leaves the published data wrong until someone notices. When every call takes the whole payload, each call corrects whatever was published before. Data that can't be computed again, such as a tenant, is different: see {ref}`interface-library-requests`.
- **Take charm-facing values.** Take charm-facing types, or plain keyword arguments for simple values. Never take the data model, a dictionary, or JSON.
- **Check leadership before writing to the application databag.** Only the leader can write it, so skip the write on other units. Don't skip writes to the unit databag, which every unit owns.
- **Raise `ValueError` for bad arguments.** A value that the interface can't represent is a mistake in the charm, so raise, and the error points at the line in the charm that passed it. Here, `FooServer` raises when it's constructed.
- **Make it idempotent.** A reconciling charm calls `publish()` in every hook, possibly more than once, and Juju runs a failed hook again, so calling `publish()` again with the same arguments must leave everything as it was. In the databag, that means writing the same keys and values every time, so that `save` sends nothing and the remote application isn't woken up for nothing. Sorting collections is part of this. Outside the databag, it means finding what an earlier call created before creating it again. For example, Juju rejects a second secret with the same label, so look up the secret by label, and only set its content if the content has changed. Juju 3.6 and later ignore identical content, but earlier versions create a new revision.

Give each publishing method its own data model, with its own fields, as `_ServerData` and `_TenantData` are.
`save` writes every field of the model that it's given, writing `None` as `null`, and leaves other keys alone.
So `publish()` and `publish_tenants()` can write to the same databag without overwriting each other, but two methods that saved the same model would.
To read the whole databag, combine the models in a class that inherits from both, as `_ProviderAppData` does.
The combined model is the one that describes the relation data format.

Nothing checks that the models don't share a field, so test it:

```py
def test_publishing_models_do_not_overlap():
    assert not _ServerData.model_fields.keys() & _TenantData.model_fields.keys()
```

If two methods have to write the same fields, load what's there, change it, and save it.

Juju applies relation data changes when the hook ends, and discards them if the hook fails, but reads within the hook return what was written.
So several writes in one hook are safe, and the remote application sees them as one change.
Each write that changes something still runs a hook command, so where one call can do the job, take everything in one call, as `publish_tenants()` does.

(interface-library-requests)=
### Answer requests

In the `foo` interface, every requirer needs a tenant, which the provider creates in its workload.
Creating a tenant can't be repeated: each attempt creates a different one.
So, unlike the servers, the charm can't pass every tenant to the library on every call.
What the library has published is the record of what was created, and it reads that back.

Give the provider a getter for the work that's still to do, a method that publishes the results, and a getter for the results that are still in use:

```py
class FooTenantRequest:
    """A requirer that's waiting for a tenant. Get these from FooProvider.get_outstanding_requests."""

    def __init__(self, relation: ops.Relation) -> None:
        self._relation = relation

    @property
    def requirer(self) -> str:
        """Name of the requiring application."""
        return self._relation.app.name

    ...  # __eq__, __hash__, and __repr__, comparing the relation ID


class FooProvider:
    ...

    def get_outstanding_requests(self) -> frozenset[FooTenantRequest]:
        """Requirers that don't have a tenant yet. Empty on a non-leader unit."""
        if not self._model.unit.is_leader():
            return frozenset()
        return frozenset(
            FooTenantRequest(relation)
            for relation in self._model.relations.get(self._relation_name, ())
            if not self._tenant(relation)
        )

    def publish_tenants(self, tenants: Mapping[FooTenantRequest, str]) -> None:
        """Tell each requirer its tenant. Other requirers' tenants are left alone.

        Does nothing on a non-leader unit.
        """
        if not all(tenants.values()):
            raise ValueError('tenant names must not be empty')
        if not self._model.unit.is_leader():
            return
        for request, tenant in tenants.items():
            request._relation.save(_TenantData(tenant=tenant), self._model.app)

    def get_unused_tenants(self, tenants: Iterable[str]) -> frozenset[str]:
        """Which of the given tenants no current requirer has been given.

        Empty on a non-leader unit. Don't call this on a unit that's being
        removed, because the relations that it's leaving still need their tenants.
        """
        if not self._model.unit.is_leader():
            return frozenset()
        relations = self._model.relations.get(self._relation_name, ())
        published = {t for relation in relations if (t := self._tenant(relation))}
        return frozenset(tenants) - published

    def _tenant(self, relation: ops.Relation) -> str | None:
        try:
            return relation.load(_TenantData, self._model.app).tenant
        except ValueError:
            return None
```

In the charm:

```py
def _reconcile(self, _: ops.EventBase):
    self.foo.publish(self._servers())
    if not self.unit.is_leader():
        return
    tenants = {
        request: self._create_tenant(request.requirer)
        for request in self.foo.get_outstanding_requests()
    }
    self.foo.publish_tenants(tenants)
    if self._stored.removing:  # see "Remove what's no longer needed by comparing"
        return
    for tenant in self.foo.get_unused_tenants(self._list_tenants()):
        self._delete_tenant(tenant)
```

Follow these rules when answering requests:

- **Work out what's outstanding from what's published.** Compare the requests with the answers already in the databag, or with the state of the workload, not with a record kept in `ops.StoredState`.
- **Say what each getter does on non-leader units.** Only the leader can read its own application databag. Return nothing if that's a safe answer, as `get_outstanding_requests()` and `get_unused_tenants()` do. If the charm might act on an empty result, raise instead, or design the getter so that an empty result is safe. A charm that deleted every tenant not returned by a getter for the tenants in use would delete them all, but a charm that deletes what `get_unused_tenants()` returns deletes nothing.
- **Give the charm request objects, not relation IDs.** A request object knows where its answer goes, so the charm never handles relation IDs or request IDs. Expose what the charm needs to make a decision, such as the name of the requiring application.
- **Take a batch of answers, and leave other answers alone.** The charm answers every outstanding request in one call. Answers to other requests stay as they are.
- **Keep answering idempotent.** Creating a tenant isn't idempotent, but the charm's reconcile handler still is: once the answers are published, the requests aren't outstanding any more, so the next call creates nothing. That's also why `publish_tenants()` can add answers without taking the whole payload, unlike `add_server()`. The library works out what's missing from what's published, so if the charm misses a call, the request is still outstanding next time.
- **Let the outstanding requests do the job of a readiness check.** The charm can call `get_outstanding_requests()` from any event, and an empty result means that there's nothing to do.
- **Let the charm remove what's no longer needed.** When a relation is removed, its relation data goes with it, but the tenant in the workload doesn't. The charm passes the tenants that it created in the workload to `get_unused_tenants()`, and deletes what it returns, except on a unit that's being removed. See {ref}`interface-library-clean-up`.

(interface-library-clean-up)=
### Remove what's no longer needed by comparing

Relation data goes away with its relation, so it never needs cleaning up.
What does is something durable that was created for a relation, such as a tenant in the workload, or a Juju secret shared over the relation.

If every requirer gets the same content, such as a CA certificate, avoid the problem: share one secret, and grant it to each relation.
Then there's nothing to remove for each relation, and Juju deletes the secret when the application is removed.

Otherwise, compare what exists with what the current relations need, and remove the difference.
Don't keep your own record of what was created: it can drift from what really exists.
Don't remove things from a dedicated `relation-broken` handler either, because `relation-broken` doesn't match up with removed relations:

- Juju runs `relation-broken` on a unit that's being removed, for each of the unit's relations, even though the relations live on.
- A removed relation might not produce `relation-broken` at all. If every unit of the application is removed, and then the relation is removed, no unit sees the relation end, and a unit added later doesn't get the event.

Comparing covers both.
During `relation-broken`, `ops` leaves the departing relation out of `model.relations`, so the leader removes its leftovers in that hook.
Anything else is removed the next time the leader compares, such as a tenant that the charm created in a hook that then failed, because Juju discarded the relation data that recorded it.
For a new leader, that's in `leader-elected`, so include it in what `events` returns.

Who compares depends on what was created:

- If the charm manages the workload, the charm knows what exists. Give it a getter that takes what exists and returns what's no longer needed, as `get_unused_tenants()` does. Return an empty result on a non-leader unit, because that's always safe. Have the charm pass only what it created for relations.
- If the library manages the workload itself, it can compare inside `sync()`. See {ref}`interface-library-real-work`.
- If the library creates a Juju secret for each relation, there isn't yet a good way to compare. `ops` can't list the secrets that a charm owns. Juju's `secret-ids` hook command can, through `ops.hookcmds`, but it returns only IDs, so finding the library's secrets by label takes a hook command for every secret that the application owns, each time the library compares. Until there's a better way, leave the secret in place. If it holds a credential that the charm created in the workload, remove the credential by comparing, so that the secret left behind can't be used. Juju deletes the secret when the application is removed.

Don't remove anything on a unit that's being removed.
Juju runs `relation-broken` for each of the unit's relations, then `stop` and `remove`, and `model.relations` shrinks with each `relation-broken`, until it's empty.
The unit stays the leader until it's gone.
That's true even when other units remain, and when the application is scaled to zero units, which keeps its relations, its relation data, and its secrets for when it's scaled up again.
So a comparison on that unit would remove everything that's still in use.
Skipping it is safe, because the next leader compares when it takes over.

`ops` doesn't say whether the unit is being removed, so the library can't tell, and the charm has to.
Before a unit that's being removed gets `relation-broken` for a relation, it gets `relation-departed` for each remote unit, with itself as the departing unit.
When only the relation is removed, the departing unit is always a remote one.
So the charm can record the first, and stop comparing from then on:

```py
class ProviderCharm(ops.CharmBase):
    _stored = ops.StoredState()

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._stored.set_default(removing=False)
        framework.observe(self.on['foo'].relation_departed, self._on_foo_departed)
        ...

    def _on_foo_departed(self, event: ops.RelationDepartedEvent):
        if event.departing_unit == self.unit:
            self._stored.removing = True
```

Say in the docstring of the method that compares that the charm mustn't use it on a unit that's being removed, as `get_unused_tenants()` does.
If the library compares inside `sync()`, have the charm say when the unit is being removed, such as with an argument to `sync()`.

(interface-library-events)=
## Support charms that handle events separately

A charm that handles each event separately doesn't have a reconcile handler to call the library from.
So that it can use the library without switching to reconciling, the library should provide an `events` method that returns the Juju events after which the charm should call it.
The method takes the charm's `on` attribute, because the library doesn't hold the charm:

```py
class FooRequirer:
    ...

    def events(self, on: ops.CharmEvents) -> tuple[ops.BoundEvent, ...]:
        """Juju events after which the server or tenant may change."""
        relation = on[self._relation_name]
        return (relation.relation_changed, relation.relation_broken)
```

The charm observes them with a handler dedicated to the library:

```py
class DeltaCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        for event in self.foo.events(self.on):
            framework.observe(event, self._on_foo_changed)

    def _on_foo_changed(self, _: ops.EventBase):
        if self.foo.is_ready():
            ...
```

What to return depends on the side of the relation:

- **For data that the library reads**, return the events after which the getters may return something different. That's usually `relation-changed` and `relation-broken` for the endpoint. During `relation-broken`, `ops` already excludes the departing relation from `model.relations`, so calling the getters gives the right answer.
- **For data that the library writes**, return the events after which the charm must publish again. That's usually only `relation-created`, because the charm already knows when its own data changes.
- **If the library depends on other events**, such as `secret-changed` for a secret shared over the relation, or `secret-expired` for a renewal deadline, include them.
- **If the library does work that only the leader does**, such as answering requests or {ref}`removing what's no longer needed <interface-library-clean-up>`, include `leader-elected`, so that a new leader picks up whatever the previous one left.

Some of these events, such as `secret-changed`, aren't specific to your library.
If two libraries return the same event, the charm's handlers for both of them run.
This is another reason for every method to be safe to call from any event.

A library can change the events that it returns in a later version, and charms that loop over the result pick up the change without any code changes.
A reconciling charm can loop over them too, by adding them to the events that it observes:

```py
self.reconcile_events = [self.on.config_changed, *self.foo.events(self.on)]
```

If a reconciling charm lists the events itself instead, it can use `events` in a unit test to check that it observes everything the library relies on.
Then a new version of the library that relies on another event fails the charm's tests, rather than its deployments.
`BoundEvent` objects don't compare equal, so compare their `event_kind`:

```py
def test_charm_observes_the_library_events():
    ctx = testing.Context(ReconcilingCharm, meta=META)
    with ctx(ctx.on.update_status(), testing.State()) as mgr:
        charm = mgr.charm
        needed = {event.event_kind for event in charm.foo.events(charm.on)}
        observed = {event.event_kind for event in charm.reconcile_events}
        assert needed <= observed
```

Some events need dedicated handling, because the library needs a value that only the event provides, such as the revision in `secret-remove`.
Document those in the class docstring, and return them from `events` only if the charm should also call the library after them, as with `secret-expired`.

Read more: {ref}`interface-library-event-values`

(interface-library-real-work)=
## Libraries that do more than read and write

Some libraries do real work for the charm.
For example, a library for a TLS certificates interface might generate a private key for each unit, publish a certificate signing request for it, and request a new certificate before the current one expires.
A library like this still shouldn't decide when its work happens.

### Do constructive work in one idempotent method

Put the work that creates or updates things in one method, such as `sync()`.
A reconciling charm calls it from its reconcile handler, and a charm that handles events separately calls it after each event that `events` returns.
In the certificates example, each call to `sync()`:

1. Looks up the unit's private key in a Juju secret, by label, and generates and stores a key only if there isn't one.
2. Publishes the certificate signing request for that key. The request is the same each time, so after the first call, `save` sends nothing.
3. Publishes a new request if the certificate is due for renewal.

Calling `sync()` again changes nothing, so the charm can call it from every event.

If the work has a deadline, such as renewing a certificate, `sync()` only does it if some event happens after the work is due and before the deadline.
Make sure that one does: set the expiry of a secret that the unit owns to the time that renewal is due, so that Juju emits `secret-expired` then, to within about a minute.
Juju emits it again every five minutes until the charm removes the expired revision.
Expiry belongs to a revision, so a new revision doesn't inherit it: set the expiry again with each renewal, and remove the old revision when it expires.
Include `secret_expired` in what `events` returns, so that the charm calls `sync()` then.
The event also says which revision expired, so the charm needs to handle it as well: see {ref}`interface-library-event-values`.

(interface-library-event-values)=
### Take values that only an event provides as arguments

Some values are only available from a particular event.
For example, when a library replaces the content of a secret that it shares over the relation, Juju emits `secret-remove` once no consumer is tracking an old revision, and only that event says which revision it is.
Provide a method that takes the values as arguments, such as `remove_revision(secret, revision)`, and say in the docstring that the charm should call it from `secret-remove`.
`secret-expired` is similar: it says which revision expired, and the event repeats until the charm removes that revision, so provide a method that takes the revision and removes it.

## Follow the naming conventions

| Thing | Use |
| --- | --- |
| Classes | `<Name>Provider`, `<Name>Requirer` |
| Charm-facing types | What the charm uses, such as `FooServer` |
| Relation argument | `relation_name` |
| Readiness | `is_ready()`, or `is_<purpose>_ready()` |
| Why it isn't ready | `rich_status()` |
| Read | `get_<thing>()`, named after what the charm uses |
| Write | `publish()`, or `publish_<thing>()` for data that's published separately |
| Work still to do | `get_outstanding_requests()` |
| Events | `events(on)` |

Use one acronym casing for every name in the library, including the data models.

## Rules at a glance

| Rule | Required? |
| --- | --- |
| Constructing the library object doesn't raise because of relation data | Must |
| The library provides a readiness check | Must |
| The readiness check has no side effects, doesn't raise because of relation data, and returns `False` when the endpoint isn't usable | Must |
| Published collections are in a stable order ({ref}`design-relation-interfaces`) | Must |
| Unit tests demonstrate the rules above | Must |
| The library is a plain class constructed from `ops.Model` | Should |
| The library doesn't emit or observe events | Should |
| The library starts with the smallest API that charms need | Should |
| The relation data format is private, and charms use their own types | Should |
| Getters don't raise once the readiness check returns `True` | Should |
| The library provides a status API | Should |
| Publishing methods write when they're called | Should |
| Every method is safe to call from any event, and publishing is idempotent | Should |
| Methods that find what to remove say that the charm mustn't use them on a unit that's being removed | Should |
| The library provides an `events` method for charms that don't reconcile | Should |
| The library follows the naming conventions | Should |

Read more: {ref}`design-relation-interfaces`, {ref}`how-to-provide-data-for-charm-tests`
