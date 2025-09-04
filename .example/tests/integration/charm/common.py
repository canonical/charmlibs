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

"""Common charm code for integration tests."""

import json
import logging

import ops

from charmlibs import example

logger = logging.getLogger(__name__)


class Charm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on['exec'].action, self._on_exec)
        self.package_version = example.__version__

    def _on_exec(self, event: ops.ActionEvent):
        logger.info('action [exec] params: %s', event.params)
        globals_dict = globals().copy()
        locals_dict = locals().copy()
        exec(event.params['code'], globals_dict, locals_dict)  # noqa: S102 (exec)
        result = locals_dict.get('result')
        logger.info('action [exec] result: %s', result)
        event.set_results({'result': json.dumps(result)})
