# charmlibs.rollingops

RollingOps is a Juju charm library for coordinating rolling operations
across application units.

It provides a single API to ensure that disruptive actions such as restarts,
reconfigurations, or maintenance tasks are executed in mutual exclusion,
with at most one unit operating at a time.

The library supports two coordination modes:

- **Peer-based (application level)**
  Uses peer relations to coordinate operations within a single application.

- **Etcd-based (cluster level)**
  Uses etcd for distributed coordination across units, enabling asynchronous,
  non-blocking execution of long-running operations.

To install, add `charmlibs-rollingops` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs import rollingops
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/rollingops) for more.

# Developing

Refer to [CONTRIBUTING.md](https://github.com/canonical/charmlibs/blob/main/CONTRIBUTING.md) for development instructions.

**Note:** Until this [issue](https://github.com/canonical/charmlibs/issues/449) is resolved,
you must explicitly set the Python version when running `just` commands:

```bash
just python=3.12 <recipe> rollingops
```
