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

"""Handler for the sysctl config.

This library allows your charm to create and configure sysctl options to the machine.

Validation and merge capabilities are added, for situations where more than one application
are setting values. The following files can be created:

- ``/etc/sysctl.d/90-juju-<app-name>``

  Requirements from one application requesting to configure the values.

- ``/etc/sysctl.d/95-juju-sysctl.conf``

  Merged file resulting from all other `90-juju-*` application files.

A charm using the sysctl lib will need a data structure like the following::

    {
        "vm.swappiness": "1",
        "vm.max_map_count": "262144",
        "vm.dirty_ratio": "80",
        "vm.dirty_background_ratio": "5",
        "net.ipv4.tcp_max_syn_backlog": "4096",
    }

Now, it can use that template within the charm, or just declare the values directly::

    from charmlibs import sysctl

    class MyCharm(CharmBase):

        def __init__(self, *args):
            ...
            self.sysctl = sysctl.Config(self.meta.name)

            self.framework.observe(self.on.install, self._on_install)
            self.framework.observe(self.on.remove, self._on_remove)

        def _on_install(self, _):
            # Alternatively, read the values from a template
            sysctl_data = {"net.ipv4.tcp_max_syn_backlog": "4096"}}

            try:
                self.sysctl.configure(config=sysctl_data)
            except (sysctl.ApplyError, sysctl.ValidationError) as e:
                logger.error(f"Error setting values on sysctl: {e.message}")
                self.unit.status = BlockedStatus("Sysctl config not possible")
            except sysctl.CommandError:
                logger.error("Error on sysctl")

        def _on_remove(self, _):
            self.sysctl.remove()
"""

from ._sysctl import (
    CHARM_FILENAME_PREFIX,
    SYSCTL_DIRECTORY,
    SYSCTL_FILENAME,
    SYSCTL_HEADER,
    ApplyError,
    CommandError,
    Config,
    Error,
    ValidationError,
)
from ._version import __version__ as __version__

__all__ = [
    'CHARM_FILENAME_PREFIX',
    'SYSCTL_DIRECTORY',
    'SYSCTL_FILENAME',
    'SYSCTL_HEADER',
    'ApplyError',
    'CommandError',
    'Config',
    'Error',
    'ValidationError',
]
