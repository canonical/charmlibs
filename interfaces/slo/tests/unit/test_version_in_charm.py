# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Light weight state-transition tests of the library in a charming context."""

import ops
import ops.testing

from charmlibs.interfaces import slo


class Charm(ops.CharmBase):
    package_version: str

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on.start, self._on_start)

    def _on_start(self, event: ops.StartEvent):
        self.package_version = slo.__version__


def test_version():
    ctx = ops.testing.Context(Charm, meta={'name': 'charm'})
    with ctx(ctx.on.start(), ops.testing.State()) as manager:
        manager.run()
        assert isinstance(manager.charm.package_version, str)
