# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Light weight state-transition tests of the library in a charming context."""

import ops
import ops.testing

from charmlibs.interfaces import http_endpoint


class Charm(ops.CharmBase):
    package_version: str

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on.start, self._on_start)

    def _on_start(self, event: ops.StartEvent):
        self.package_version = http_endpoint.__version__


def test_version():
    ctx = ops.testing.Context(Charm, meta={'name': 'charm'})
    with ctx(ctx.on.start(), ops.testing.State()) as manager:
        manager.run()
        assert isinstance(manager.charm.package_version, str)
