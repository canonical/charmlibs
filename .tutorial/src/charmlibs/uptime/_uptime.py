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

"""Private module defining the core logic of the uptime package."""

import datetime

import psutil


def uptime() -> datetime.timedelta:
    """Get the uptime for the system where the charm is running."""
    utc = datetime.timezone.utc
    utc_now = datetime.datetime.now(tz=utc)
    utc_boot_time = datetime.datetime.fromtimestamp(psutil.boot_time(), tz=utc)
    return utc_now - utc_boot_time
