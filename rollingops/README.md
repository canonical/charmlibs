# charmlibs.rollingops

The `rollingops` library.

`rollingops` provides a rolling-operations manager for Juju charms backed by etcd.

It coordinates operations across units by using etcd as a shared lock and queue backend,
and uses TLS client credentials to authenticate requests to the etcd cluster.

To install, add `charmlibs-rollingops` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs import rollingops
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/rollingops) for more.

## Unit tests
```py
just python=3.12 unit rollingops
```
## Pack
```py
just python=3.12  pack-machine rollingops
```
## Integration tests
```py
just python=3.12  integration-machine rollingops
```
