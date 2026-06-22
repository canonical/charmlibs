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

"""Manage TLS certificates using the ``tls-certificates`` interface (V1).

This library implements the Requirer and Provider roles for the ``k8s_backup_target`` relation,
in the :class:`TLSCertificatesRequiresV4` and :class:`TLSCertificatesProvidesV4` classes.

Read more:

- `Tutorial <https://documentation.ubuntu.com/charmlibs/tutorials/charmlibs/interfaces/tls-certificates/tutorial/>`_
- `Library reference <https://documentation.ubuntu.com/charmlibs/reference/charmlibs/interfaces/tls-certificates/>`_
- `How to configure certificate requests <https://documentation.ubuntu.com/charmlibs/how-to/charmlibs/interfaces/tls-certificates/configure-certificate-requests/>`_
- `Explanation of the library design <https://documentation.ubuntu.com/charmlibs/explanation/charmlibs/interfaces/tls-certificates/design/>`_
"""

from ._tls_certificates import (
    Certificate,
    CertificateAvailableEvent,
    CertificateDeniedEvent,
    CertificateError,
    CertificateRequestAttributes,
    CertificateRequestErrorCode,
    CertificateSigningRequest,
    CertificatesRequirerCharmEvents,
    DataValidationError,
    Mode,
    PrivateKey,
    ProviderCertificate,
    ProviderCertificateError,
    RequirerCertificateRequest,
    TLSCertificatesError,
    TLSCertificatesProvidesV4,
    TLSCertificatesRequiresV4,
    calculate_relative_datetime,
    chain_has_valid_order,
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)
from ._version import __version__ as __version__

__all__ = [
    "Certificate",
    "CertificateAvailableEvent",
    "CertificateDeniedEvent",
    "CertificateError",
    "CertificateRequestAttributes",
    "CertificateRequestErrorCode",
    "CertificateSigningRequest",
    "CertificatesRequirerCharmEvents",
    "DataValidationError",
    "Mode",
    "PrivateKey",
    "ProviderCertificate",
    "ProviderCertificateError",
    "RequirerCertificateRequest",
    # only the names listed in __all__ are imported when executing:
    # from charmlibs.tls_certificates import *
    "TLSCertificatesError",
    "TLSCertificatesProvidesV4",
    "TLSCertificatesRequiresV4",
    "calculate_relative_datetime",
    "chain_has_valid_order",
    "generate_ca",
    "generate_certificate",
    "generate_csr",
    "generate_private_key",
]
