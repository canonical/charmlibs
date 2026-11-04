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

"""Library to manage the integration with the SMTP Integrator charm.

This library contains the Requires and Provides classes for handling the integration
between an application and a charm providing the `smtp` and `smtp-legacy` integrations.
If the requirer charm supports secrets, the preferred approach is to use the `smtp`
relation to leverage them.
This library also contains a `SmtpRelationData` class to wrap the SMTP data that will
be shared via the integration.

### Requirer Charm

```python

from charmlibs.interfaces.smtp import SmtpDataAvailableEvent, SmtpRequires

class SmtpRequirerCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.smtp = SmtpRequires(self)
        self.framework.observe(self.smtp.on.smtp_data_available, self._handler)
        ...

    def _handler(self, events: SmtpDataAvailableEvent) -> None:
        ...

```

As shown above, the library provides a custom event to handle the scenario in
which new SMTP data has been added or updated.

### Provider Charm

Following the previous example, this is an example of the provider charm.

```python
from charmlibs.interfaces.smtp import SmtpProvides

class SmtpProviderCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.smtp = SmtpProvides(self)
        ...

```
The SmtpProvides object wraps the list of relations into a `relations` property
and provides an `update_relation_data` method to update the relation data by passing
a `SmtpRelationData` data object.

```python
class SmtpProviderCharm(ops.CharmBase):
    ...

    def _on_config_changed(self, _) -> None:
        for relation in self.model.relations[self.smtp.relation_name]:
            self.smtp.update_relation_data(relation, self._get_smtp_data())

```
"""

from ._smtp import (
    DEFAULT_RELATION_NAME,
    LEGACY_RELATION_NAME,
    AuthType,
    SecretError,
    SmtpDataAvailableEvent,
    SmtpError,
    SmtpProvides,
    SmtpRelationData,
    SmtpRequires,
    SmtpRequiresEvents,
    TransportSecurity,
    parse_recipients,
    recipients_validator,
)
from ._version import __version__ as __version__

__all__ = [
    'DEFAULT_RELATION_NAME',
    'LEGACY_RELATION_NAME',
    'AuthType',
    'SecretError',
    'SmtpDataAvailableEvent',
    'SmtpError',
    'SmtpProvides',
    'SmtpRelationData',
    'SmtpRequires',
    'SmtpRequiresEvents',
    'TransportSecurity',
    'parse_recipients',
    'recipients_validator',
]
