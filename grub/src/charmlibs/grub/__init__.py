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

r"""Simple library for managing Linux kernel configuration via GRUB.

This library is only used for setting additional parameters that will be stored in the
``/etc/default/grub.d/95-juju-charm.cfg`` config file and not for editing other
configuration files. It's intended to be used in charms to help configure the machine.

Configurations for individual charms will be stored in ``/etc/default/grub.d/90-juju-<charm>``,
but these configurations will only have informational value as all configurations will be merged
to ``/etc/default/grub.d/95-juju-charm.cfg``.

Example of use::

    class UbuntuCharm(CharmBase):
        def __init__(self, *args):
            ...
            self.framework.observe(self.on.install, self._on_install)
            self.framework.observe(self.on.update_status, self._on_update_status)
            self.framework.observe(self.on.remove, self._on_remove)
            self.grub = grub.GrubConfig(self.meta.name)
            log.debug("found keys %s in GRUB config file", self.grub.keys())

        def _on_install(self, _):
            try:
                self.grub.update(
                    {"GRUB_CMDLINE_LINUX_DEFAULT": "$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G"}
                )
            except grub.ValidationError as error:
                self.unit.status = BlockedStatus(f"[{error.key}] {error.message}")

        def _on_update_status(self, _):
            if self.grub["GRUB_CMDLINE_LINUX_DEFAULT"] != "$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G":
                self.unit.status = BlockedStatus("wrong GRUB configuration")

        def _on_remove(self, _):
            self.grub.remove()
"""

from ._grub import (
    ApplyError,
    Config,
    IsContainerError,
    ValidationError,
    check_update_grub,
    is_container,
)
from ._version import __version__ as __version__

__all__ = [
    'ApplyError',
    'Config',
    'IsContainerError',
    'ValidationError',
    'check_update_grub',
    'is_container',
]
