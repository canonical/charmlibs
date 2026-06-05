---
myst:
  html_meta:
    description: Manage files in a charm workload with pathops.
---

# Getting started

This tutorial shows you how to use ``pathops`` to manage files in a charm workload — writing config, restarting only when something changes, and testing it all with ``ops.testing``.

## Write a config file with ``ensure_contents``

The most common thing charms do with files is write a configuration file and restart the workload if the file changed. ``pathops.ensure_contents`` does exactly this — it compares the file's current contents, permissions, and ownership against what you pass in, only writes if something differs, and returns ``True`` if any changes were made.

Start with a base charm class that defines the config-changed handler and stubs out ``root`` and ``_restart_workload`` for subclasses to implement:

```python
import ops
from charmlibs import pathops


class MyCharmBase(ops.CharmBase):

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    @property
    def root(self) -> pathops.PathProtocol:
        raise NotImplementedError

    def _restart_workload(self) -> None:
        raise NotImplementedError

    def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
        config = f'port: {self.config["port"]}\n'
        changed = pathops.ensure_contents(self.root / 'etc' / 'myapp' / 'config.yaml', config)
        if changed:
            self._restart_workload()
```

The event handler doesn't know or care whether it's running on K8s or a machine — it just uses ``self.root`` to build paths with the ``/`` operator, exactly like ``pathlib``.

Now implement the K8s subclass:

```python
class MyK8sCharm(MyCharmBase):

    @property
    def root(self) -> pathops.ContainerPath:
        container = self.unit.get_container('myapp')
        return pathops.ContainerPath('/', container=container)

    def _restart_workload(self) -> None:
        container = self.unit.get_container('myapp')
        container.restart('myapp')
```

## Make it work on machines too

The same pattern works for machine charms — just implement the stubs with ``LocalPath``:

```python
class MyMachineCharm(MyCharmBase):

    @property
    def root(self) -> pathops.LocalPath:
        return pathops.LocalPath('/')

    def _restart_workload(self) -> None:
        subprocess.run(['systemctl', 'restart', 'myapp'], check=True)
```

The ``_on_config_changed`` handler in the base class works unchanged — ``ensure_contents`` accepts any ``PathProtocol``, which both ``ContainerPath`` and ``LocalPath`` satisfy.

## Test it with ``ops.testing``

Because ``pathops`` works through the standard ``ops.Container`` interface, ``ops.testing`` state-transition tests work out of the box — no extra mocking needed:

```python
from ops import testing

from charm import MyK8sCharm


def test_config_changed_writes_config():
    ctx = testing.Context(MyK8sCharm)
    container = testing.Container('myapp', can_connect=True)
    state_in = testing.State(containers={container}, config={'port': 8080})

    state_out = ctx.run(ctx.on.config_changed(), state_in)

    fs = state_out.get_container('myapp').get_filesystem(ctx)
    assert (fs / 'etc' / 'myapp' / 'config.yaml').read_text() == 'port: 8080\n'
```

``get_filesystem`` returns a ``pathlib.Path`` to the temporary directory that ``ops.testing`` uses to simulate the container filesystem. Files written by ``pathops.ContainerPath`` during the event handler end up there, so you can assert on them with plain ``pathlib``.

## See also

- {external+ops:ref}`files-in-containers`
- {external+ops:ref}`write-unit-tests-for-a-charm`
