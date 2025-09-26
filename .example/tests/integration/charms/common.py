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

"""Common charm code for integration test charms.

This file is symlinked alongside src/charm.py by these charms.
"""

import logging

import ops

from charmlibs import example

logger = logging.getLogger(__name__)


class Charm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on['lib-version'].action, self._on_lib_version)

    def _on_lib_version(self, event: ops.ActionEvent):
        logger.info('action [lib-version] called with params: %s', event.params)
        results = {'version': example.__version__}
        event.set_results(results)
        logger.info('action [lib-version] set_results: %s', results)
