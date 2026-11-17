# Contributing to charmlibs.interfaces.tracing

## Formatting and linting

```
just format interfaces/tracing
just lint interfaces/tracing
```

## Unit tests

```
just unit interfaces/tracing
```

## Integration tests

`charmlibs.interfaces.tracing` was migrated from `charms.tempo_coordinator_k8s.v0.tracing`. The Charmlibs version doesn't have its own integration tests. To test a development version of `charmlibs.interfaces.tracing`, we recommend temporarily patching [tempo-operators](https://github.com/canonical/tempo-operators) and running its integration tests.

To patch tempo-operators, run this command in the `coordinator` directory:

```
uv add git+https://github.com/<user>/charmlibs@<branch>#subdirectory=interfaces/tracing
```

Make sure that `<user>` and `<branch>` point to the development version of `charmlibs.interfaces.tracing`.

Next, in the Python source files under `coordinator/src/`, replace:

```py
from charms.tempo_coordinator_k8s.v0.tracing import ...
```

With:

```py
from charmlibs.interfaces.tracing import ...
```

> TODO: Drop this replacement step after tempo-operators adopts `charmlibs.interfaces.tracing`.

Then run the tempo-operators integration tests as normal.

## Documentation

The [reference documentation](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tracing) is generated from Python docstrings. The introductory text comes from [`__init.py__`](src/charmlibs/interfaces/tracing/__init__.py).

To build the docs locally:

```
just docs html interfaces/tracing
```

The built docs are in [`.docs/_build/html/`](../../.docs/_build/html/) under the repository root.
