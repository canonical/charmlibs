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

"""Transfer x.509 certificates using the ``certificate-transfer`` interface (V1).

This is a port of ``certificate_transfer_interface.certificate_transfer`` v1.15.

This library contains the Requires and Provides classes for handling the
certificate-transfer interface. It supports both v0 and v1 of the interface.

For requirers, they will set version 1 in their application databag as a hint to
the provider. They will read the databag from the provider first as v1, and fallback
to v0 if the format does not match.

For providers, they will check the version in the requirer's application databag,
and send v1 if that version is set to 1, otherwise it will default to 0 for backwards
compatibility.

=================
Getting Started
=================

From a charm directory, fetch the library using `charmcraft`:

::

    charmcraft fetch-lib charms.certificate_transfer_interface.v1.certificate_transfer

=================
Provider charm
=================

The provider charm is the charm providing public certificates to another charm that requires them.

Example:

::

    from ops.charm import CharmBase, RelationJoinedEvent
    from ops.main import main

    from lib.charms.certificate_transfer_interface.v1.certificate_transfer import (
        CertificateTransferProvides,
    )

    class DummyCertificateTransferProviderCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.certificate_transfer = CertificateTransferProvides(self, "certificates")
            self.framework.observe(
                self.on.certificates_relation_joined, self._on_certificates_relation_joined
            )

        def _on_certificates_relation_joined(self, event: RelationJoinedEvent):
            certificate = "my certificate"
            self.certificate_transfer.add_certificates(certificate)


    if __name__ == "__main__":
        main(DummyCertificateTransferProviderCharm)


=================
Requirer charm
=================
The requirer charm is the charm requiring certificates from another charm that provides them.

Example:

::

    import logging

    from ops.charm import CharmBase
    from ops.main import main

    from lib.charms.certificate_transfer_interface.v1.certificate_transfer import (
        CertificatesAvailableEvent,
        CertificatesRemovedEvent,
        CertificateTransferRequires,
    )


    class DummyCertificateTransferRequirerCharm(CharmBase):
        def __init__(self, *args):
            super().__init__(*args)
            self.certificate_transfer = CertificateTransferRequires(self, "certificates")
            self.framework.observe(
                self.certificate_transfer.on.certificate_set_updated, self._on_certificates_available
            )
            self.framework.observe(
                self.certificate_transfer.on.certificates_removed, self._on_certificates_removed
            )

        def _on_certificates_available(self, event: CertificatesAvailableEvent):
            logging.info(event.certificates)
            logging.info(event.relation_id)

        def _on_certificates_removed(self, event: CertificatesRemovedEvent):
            logging.info(event.relation_id)


    if __name__ == "__main__":
        main(DummyCertificateTransferRequirerCharm)

You can integrate both charms by running:

::

    juju integrate <certificate_transfer provider charm> <certificate_transfer requirer charm>

"""

from ._certificate_transfer import (
    CertificatesAvailableEvent,
    CertificatesRemovedEvent,
    CertificateTransferProvides,
    CertificateTransferRequires,
    DataValidationError,
    TLSCertificatesError,
)
from ._version import __version__ as __version__

__all__ = [
    "CertificateTransferProvides",
    "CertificateTransferRequires",
    "CertificatesAvailableEvent",
    "CertificatesRemovedEvent",
    "DataValidationError",
    "TLSCertificatesError",
]
