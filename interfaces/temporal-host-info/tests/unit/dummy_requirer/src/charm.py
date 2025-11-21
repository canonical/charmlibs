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

from typing import Any

from ops.charm import CharmBase
from ops.main import main
from scenario import ActiveStatus

from charmlibs.interfaces.temporal_host_info import TemporalHostInfoRequirer


class DummyHostInfoRequirerCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.host_info = TemporalHostInfoRequirer(self)
        self.framework.observe(
            self.host_info.on.temporal_host_info_available, self._on_host_info_available
        )

    def _on_host_info_available(self, event: Any) -> None:
        host = self.host_info.host
        port = self.host_info.port
        self.unit.status = ActiveStatus(f'Host: {host}, Port: {port}')


if __name__ == '__main__':
    main(DummyHostInfoRequirerCharm)
