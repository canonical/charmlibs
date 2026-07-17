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

"""Example requirer charm for unit tests."""

import ops

# from charmlibs.interfaces import {{ cookiecutter.__pkg }}

META = {
    'name': 'requirer',
    'requires': {'endpoint': {'interface': '{{ cookiecutter.project_slug }}'}},
}


class RequirerCharm(ops.CharmBase):
    """A minimal requirer charm for testing the {{ cookiecutter.project_slug }} interface."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        # self.lib_obj = {{ cookiecutter.__pkg }}.<...>Requirer(self, 'endpoint', ...)
        framework.observe(self.on.update_status, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        # Do something with self.lib_obj to assert on in tests.
        ...
