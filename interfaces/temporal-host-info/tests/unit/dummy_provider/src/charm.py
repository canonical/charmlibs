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

from charmlibs.interfaces.temporal_host_info import TemporalHostInfoProvider


class DummyHostInfoProviderCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.host_info = TemporalHostInfoProvider(self, port=7233)


if __name__ == '__main__':
    main(DummyHostInfoProviderCharm)
