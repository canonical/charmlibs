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

Learn more about how to use the TLS Certificates interface library by reading the
[usage documentation on Charmhub](https://charmhub.io/certificate-transfer-interface/).
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
