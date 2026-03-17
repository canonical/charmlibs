# charmlibs.advanced_rollingops

The `advanced-rollingops` library.

`advanced_rollingops` provides a rolling-operations manager for Juju charms backed by etcd.

It coordinates operations across units by using etcd as a shared lock and queue backend,
and uses TLS client credentials to authenticate requests to the etcd cluster.

To install, add `charmlibs-advanced-rollingops` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs import advanced_rollingops
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/advanced_rollingops) for more.

## Unit tests
```py
just python=3.12 unit advanced-rollingops
```
## Pack
```py
just python=3.12  pack-machine advanced-rollingops
```
## Integration tests
```py
just python=3.12  integration-machine advanced-rollingops
```
