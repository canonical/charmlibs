# charmlibs-snap

`snap` manages snaps on the machine a charm runs on, by talking to `snapd` over its REST API. Function names, arguments, and error behaviour follow the `snap` command line, so what you know from the CLI carries over.

To install, add `charmlibs-snap` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs import snap
```

See the [reference documentation](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/snap) for more.

Upgrading from 1.x? Version 2.0 is a rewrite with a new API -- see [how to migrate from 1.x to 2.0](https://canonical.com/juju/docs/charmlibs/how-to/charmlibs/snap/migrate-from-1x). This README and the library docs cover the 2.x series; for 1.x, see the [snap-v1.0.1.post0 tag](https://github.com/canonical/charmlibs/tree/snap-v1.0.1.post0/snap).

# Getting started

Every operation is a module-level function that takes the snap's name. To make sure a snap is installed on a particular channel, and refresh it if an update is available:

```py
from charmlibs import snap

snap.ensure_installed('lxd', '5.21/stable')
```

`ensure_installed` installs the snap if it's absent, refreshes it if it's on the wrong channel or revision, and otherwise refreshes it if an update is available. It returns a truthy value if anything changed.

Configure the snap and manage its services:

```py
snap.set('lxd', {'core.https_address': ':8443'})
snap.get_one('lxd', 'core.https_address')  # ':8443'
snap.start('lxd', 'daemon', enable=True)
```

Query the installed snap's state with `list_one`, which returns an `InstalledInfo`:

```py
info = snap.list_one('lxd')
info.tracking  # '5.21/stable'
info.revision  # '33110'
info.version  # '5.21.3'
```

Install or refresh to a specific revision, and `hold` the snap so that automatic refreshes don't move it:

```py
snap.refresh('lxd', '5.21/stable', revision=33110)
snap.hold('lxd')
```

Also available: `install`, `remove`, `unhold`, `stop`, `restart`, `get`, `unset`, `connect`, `disconnect`, `alias`, `unalias`, and `logs`.

# Errors

Every error the library raises is a subclass of `snap.Error`, so `except snap.Error` catches anything that went wrong talking to snapd. Invalid arguments raise ordinary Python exceptions such as `ValueError`.

When snapd reports an error, the library raises `snap.APIError`, narrowed to a specific subclass where a charm might want to handle the case -- for example `NotInstalledError`, `NotInStoreError`, `ChannelNotAvailableError`, `NeedsClassicError`, or `ChangeError` (a change that failed after starting, such as an install hook erroring). Each function documents the errors it raises.

When snapd can't be reached or understood, the library raises `snap.ConnectionError` -- or its subclass `snap.SocketNotFoundError`, which usually means snapd isn't installed -- `snap.TimeoutError` (snapd didn't answer in time), or `snap.BadResponseError` (a response the library can't read, which should be reported as a bug).
