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

"""Abstractions for stopping, starting and managing system services via systemd.

For the most part, we transparently provide an interface to a commonly used selection of
systemd commands, with a few shortcuts baked in. For example, :func:`service_pause` and
:func:`service_resume` will run the mask/unmask and enable/disable invocations.

Example usage
-------------

.. code-block:: python

    from charmlibs import systemd

    # Start a service
    if not systemd.service_running("mysql"):
        success = systemd.service_start("mysql")

    # Attempt to reload a service, restarting if necessary
    success = systemd.service_reload("nginx", restart_on_failure=True)
"""

from ._systemd import (
    SystemdError,
    daemon_reload,
    service_disable,
    service_enable,
    service_failed,
    service_pause,
    service_reload,
    service_restart,
    service_resume,
    service_running,
    service_start,
    service_stop,
)
from ._version import __version__ as __version__

__all__ = [
    'SystemdError',
    'daemon_reload',
    'service_disable',
    'service_enable',
    'service_failed',
    'service_pause',
    'service_reload',
    'service_restart',
    'service_resume',
    'service_running',
    'service_start',
    'service_stop',
]
