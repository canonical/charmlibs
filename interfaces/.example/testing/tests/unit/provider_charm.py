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

"""Example provider charm for unit tests."""

import ops

# from charmlibs.interfaces import example_interface

META = {
    'name': 'provider',
    'provides': {'endpoint': {'interface': 'example-interface'}},
}


class ProviderCharm(ops.CharmBase):
    """A minimal provider charm for testing the example-interface interface."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        # self.lib_obj = example_interface.<...>Provider(self, 'endpoint', ...)
        framework.observe(self.on.update_status, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        # Do something with self.lib_obj to assert on in tests.
        ...
