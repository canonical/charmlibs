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

import logging
import os
from datetime import timedelta
from pathlib import Path

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateRequestAttributes,
    CertificateSigningRequest,
    PrivateKey,
)

logger = logging.getLogger(__name__)


class CertificatesManager:
    """Manage generation and persistence of TLS certificates for etcd client access.

    This class is responsible for creating and storing a client Certificate
    Authority (CA) and a client certificate/key pair used to authenticate
    with etcd via TLS. Certificates are generated only once and persisted
    under a local directory so they can be reused across charm executions.

    Certificates are valid for 20 years. They are not renewed or rotated.
    """

    BASE_DIR = Path('/var/lib/rollingops/tls')

    CA_CERT = BASE_DIR / 'client-ca.pem'
    CLIENT_KEY = BASE_DIR / 'client.key'
    CLIENT_CERT = BASE_DIR / 'client.pem'

    VALIDITY_DAYS = 365 * 20

    @classmethod
    def _exists(cls) -> bool:
        """Check whether the client certificates and CA certificate already exist."""
        return cls.CA_CERT.exists() and cls.CLIENT_KEY.exists() and cls.CLIENT_CERT.exists()

    @classmethod
    def client_paths(cls) -> tuple[Path, Path]:
        """Return filesystem paths for the client certificate and key.

        Returns:
            A tuple containing:
            - Path to the client certificate
            - Path to the client private key
        """
        return cls.CLIENT_CERT, cls.CLIENT_KEY

    @classmethod
    def persist_client_cert_key_and_ca(cls, cert_pem: str, key_pem: str, ca_pem: str) -> None:
        """Persist the provided client certificate, key, and CA to disk.

        Args:
            cert_pem: PEM-encoded client certificate.
            key_pem: PEM-encoded client private key.
            ca_pem: PEM-encoded CA certificate.
        """
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)

        cls.CLIENT_CERT.write_text(cert_pem)
        cls.CLIENT_KEY.write_text(key_pem)
        cls.CA_CERT.write_text(ca_pem)

        os.chmod(cls.CLIENT_CERT, 0o644)
        os.chmod(cls.CLIENT_KEY, 0o600)
        os.chmod(cls.CA_CERT, 0o644)

    @classmethod
    def has_client_cert_key_and_ca(cls, cert_pem: str, key_pem: str, ca_pem: str) -> bool:
        """Return whether the provided certificate material matches local files."""
        if not cls.CLIENT_CERT.exists() or not cls.CLIENT_KEY.exists() or not cls.CA_CERT.exists():
            return False

        return (
            cls.CLIENT_CERT.read_text() == cert_pem
            and cls.CLIENT_KEY.read_text() == key_pem
            and cls.CA_CERT.read_text() == ca_pem
        )

    @classmethod
    def generate(cls, common_name: str) -> tuple[str, str, str]:
        """Generate a client CA and client certificate if they do not exist.

        This method creates:
        1. A CA private key and self-signed CA certificate.
        2. A client private key.
        3. A certificate signing request (CSR) using the provided common name.
        4. A client certificate signed by the generated CA.

        The generated files are written to disk and reused in future runs.
        If the certificates already exist, this method does nothing.

        Args:
            common_name: Common Name (CN) used in the client certificate
                subject. This value should not contain slashes.

        Returns:
            A tuple containing:
            - The client certificate PEM string
            - The client private key PEM string
            - The client CA certificate PEM string
        """
        if cls._exists():
            return cls.CLIENT_CERT.read_text(), cls.CLIENT_KEY.read_text(), cls.CA_CERT.read_text()

        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)

        ca_key = PrivateKey.generate(key_size=4096)
        ca_attributes = CertificateRequestAttributes(
            common_name='rollingops-client-ca', is_ca=True
        )
        ca_crt = Certificate.generate_self_signed_ca(
            attributes=ca_attributes,
            private_key=ca_key,
            validity=timedelta(days=cls.VALIDITY_DAYS),
        )

        client_key = PrivateKey.generate(key_size=4096)

        csr_attributes = CertificateRequestAttributes(
            common_name=common_name, add_unique_id_to_subject_name=False
        )
        csr = CertificateSigningRequest.generate(
            attributes=csr_attributes,
            private_key=client_key,
        )

        client_crt = Certificate.generate(
            csr=csr,
            ca=ca_crt,
            ca_private_key=ca_key,
            validity=timedelta(days=cls.VALIDITY_DAYS),
            is_ca=False,
        )

        cls.CA_CERT.write_text(ca_crt.raw)
        cls.CLIENT_KEY.write_text(client_key.raw)
        cls.CLIENT_CERT.write_text(client_crt.raw)

        os.chmod(cls.CLIENT_KEY, 0o600)
        os.chmod(cls.CA_CERT, 0o644)
        os.chmod(cls.CLIENT_CERT, 0o644)

        return client_crt.raw, client_key.raw, ca_crt.raw
