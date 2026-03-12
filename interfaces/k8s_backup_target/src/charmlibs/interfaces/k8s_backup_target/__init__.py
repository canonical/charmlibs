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

"""K8s Backup Target library.

This library implements the Requirer and Provider roles for the ``k8s_backup_target`` relation
interface. It is used by client charms to declare backup specifications, and by backup charms or
backup integrator charms to consume them and forward to backup operators.

The ``k8s_backup_target`` interface allows a charm (the provider) to provide a declarative
description of what Kubernetes resources should be included in a backup. These specifications are
sent to the backup charm or backup integrator charm (the requirer), which merges them with schedule
configuration and forwards to the backup operator.

This interface follows a least-privilege model: client charms do not manipulate cluster resources
themselves. Instead, they define what should be backed up and leave execution to the backup
operator.

Provider Example
================

::

    from charmlibs.interfaces.k8s_backup_target import (
        K8sBackupTargetProvider,
        K8sBackupTargetSpec,
    )

    class SomeCharm(CharmBase):
        def __init__(self, *args):
            # ...
            self.backup = K8sBackupTargetProvider(
                self,
                relation_name="backup",
                spec=K8sBackupTargetSpec(
                    include_namespaces=["my-namespace"],
                    include_resources=["persistentvolumeclaims", "services", "deployments"],
                    ttl=str(self.config["ttl"]),
                ),
                # Optional: refresh the data on custom events
                refresh_event=[self.on.config_changed],
            )

Requirer Example
================

::

    from charmlibs.interfaces.k8s_backup_target import (
        K8sBackupTargetRequirer,
    )

    class BackupIntegratorCharm(CharmBase):
        def __init__(self, *args):
            # ...
            self.backup_requirer = K8sBackupTargetRequirer(self, relation_name="k8s-backup-target")

        def _on_backup_action(self, event):
            spec = self.backup_requirer.get_backup_spec(
                app_name=event.params["app"],
                endpoint=event.params["endpoint"],
                model=event.params["model"],
            )
            ...
"""

from ._backup_target import (
    K8sBackupTargetProvider,
    K8sBackupTargetRequirer,
)
from ._schema import K8sBackupTargetSpec
from ._version import __version__ as __version__

__all__ = [
    "K8sBackupTargetProvider",
    "K8sBackupTargetRequirer",
    "K8sBackupTargetSpec",
]
