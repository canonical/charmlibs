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

"""Manage TLS certificates using the ``tls_certificates`` interface (V1).

This is a port of ``tls_certificates_interface.tls_certificates`` v4.22.

Learn more on how-to use the TLS Certificates interface library by reading the documentation:

* https://charmhub.io/tls-certificates-interface/
"""

from ._tls_certificates import (
    Certificate,
    CertificateAvailableEvent,
    CertificateRequestAttributes,
    CertificateSigningRequest,
    CertificatesRequirerCharmEvents,
    DataValidationError,
    Mode,
    PrivateKey,
    ProviderCertificate,
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
    "CertificateRequestAttributes",
    "CertificateSigningRequest",
    "CertificatesRequirerCharmEvents",
    "DataValidationError",
    "Mode",
    "PrivateKey",
    "ProviderCertificate",
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
