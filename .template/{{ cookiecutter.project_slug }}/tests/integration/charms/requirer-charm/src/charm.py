# Copyright 2026 Canonical Ltd.
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

"""Requirer charm for integration tests."""

import logging

import common
import ops

logger = logging.getLogger(__name__)

ENDPOINT = 'endpoint'


class Charm(common.Charm):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        # self.lib_obj = {{ cookiecutter.__pkg }}.<...>Requirer(self, ENDPOINT, ...)
        framework.observe(self.on[ENDPOINT].relation_changed, self._reconcile)
        framework.observe(self.on.start, self._on_start)

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        self.unit.status = ops.ActiveStatus()

    def _reconcile(self, event: ops.RelationChangedEvent):
        """Handle endpoint relation events."""
        # Do something with self.lib_obj here.
        ...


if __name__ == '__main__':  # pragma: nocover
    ops.main(Charm)
