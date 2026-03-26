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

"""Manage generation and persistence of TLS certificates for etcd client access.

This file contains functions responsible for creating and storing a client Certificate
Authority (CA) and a client certificate/key pair used to authenticate
with etcd via TLS. Certificates are generated only once and persisted
under a local directory so they can be reused across charm executions.

Certificates are valid for 20 years. They are not renewed or rotated.
"""

from datetime import timedelta

from charmlibs import pathops
from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateRequestAttributes,
    CertificateSigningRequest,
    PrivateKey,
)
from charmlibs.rollingops._models import (
    RollingOpsFileSystemError,
    SharedCertificate,
    with_pebble_retry,
)

BASE_DIR = pathops.LocalPath('/var/lib/rollingops/tls')
CA_CERT_PATH = BASE_DIR / 'client-ca.pem'
CLIENT_KEY_PATH = BASE_DIR / 'client.key'
CLIENT_CERT_PATH = BASE_DIR / 'client.pem'
VALIDITY_DAYS = 365 * 50
KEY_SIZE = 4096


def persist_client_cert_key_and_ca(shared: SharedCertificate) -> None:
    """Persist the provided client certificate, key, and CA to disk.

    Raises:
        PebbleConnectionError: if the remote container cannot be reached
        RollingOpsFileSystemError: if there is a problem when writing the certificates
    """
    if _has_client_cert_key_and_ca(shared):
        return
    try:
        _mkdir_with_retry(BASE_DIR)
        _write_text_with_retry(path=CLIENT_CERT_PATH, content=shared.certificate, mode=0o644)
        _write_text_with_retry(path=CLIENT_KEY_PATH, content=shared.key, mode=0o600)
        _write_text_with_retry(path=CA_CERT_PATH, content=shared.ca, mode=0o644)

    except (FileNotFoundError, LookupError, NotADirectoryError, PermissionError) as e:
        raise RollingOpsFileSystemError('Failed to persist client certificates and key.') from e


def _has_client_cert_key_and_ca(shared: SharedCertificate) -> bool:
    """Return whether the provided certificate material matches local files.

    Raises:
        PebbleConnectionError: if the remote container cannot be reached
        RollingOpsFileSystemError: if there is a problem when writing the certificates
    """
    if not _exists():
        return False
    try:
        return (
            _read_text_with_retry(CLIENT_CERT_PATH) == shared.certificate
            and _read_text_with_retry(CLIENT_KEY_PATH) == shared.key
            and _read_text_with_retry(CA_CERT_PATH) == shared.ca
        )
    except (FileNotFoundError, IsADirectoryError, PermissionError) as e:
        raise RollingOpsFileSystemError('Failed to read certificates and key.') from e


def generate(common_name: str) -> SharedCertificate:
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

    Raises:
        PebbleConnectionError: if the remote container cannot be reached
        RollingOpsFileSystemError: if there is a problem when writing the certificates
    """
    if _exists():
        return SharedCertificate(
            certificate=_read_text_with_retry(CLIENT_CERT_PATH),
            key=_read_text_with_retry(CLIENT_KEY_PATH),
            ca=_read_text_with_retry(CA_CERT_PATH),
        )

    ca_key = PrivateKey.generate(key_size=KEY_SIZE)
    ca_attributes = CertificateRequestAttributes(
        common_name=common_name,
        sans_dns=[common_name],
        is_ca=True,
        add_unique_id_to_subject_name=False,
    )
    ca_crt = Certificate.generate_self_signed_ca(
        attributes=ca_attributes,
        private_key=ca_key,
        validity=timedelta(days=VALIDITY_DAYS),
    )

    client_key = PrivateKey.generate(key_size=KEY_SIZE)

    csr_attributes = CertificateRequestAttributes(
        common_name=common_name, sans_dns=[common_name], add_unique_id_to_subject_name=False
    )
    csr = CertificateSigningRequest.generate(
        attributes=csr_attributes,
        private_key=client_key,
    )

    client_crt = Certificate.generate(
        csr=csr,
        ca=ca_crt,
        ca_private_key=ca_key,
        validity=timedelta(days=VALIDITY_DAYS),
        is_ca=False,
    )

    shared = SharedCertificate(
        certificate=client_crt.raw,
        key=client_key.raw,
        ca=ca_crt.raw,
    )

    persist_client_cert_key_and_ca(shared)
    return shared


def _exists() -> bool:
    """Check whether the client certificates and CA certificate already exist.

    Raises:
        PebbleConnectionError: if the remote container cannot be reached
    """
    return (
        _exists_with_retry(CA_CERT_PATH)
        and _exists_with_retry(CLIENT_KEY_PATH)
        and _exists_with_retry(CLIENT_CERT_PATH)
    )


def _exists_with_retry(path: pathops.LocalPath) -> bool:
    """Check whether a path exists, retrying on transient Pebble errors.

    Args:
        path: The path to check.

    Returns:
        True if the path exists, False otherwise.

    Raises:
        PebbleConnectionError: If the remote container cannot be reached after retries.
    """
    return with_pebble_retry(lambda: path.exists())


def _read_text_with_retry(path: pathops.LocalPath) -> str:
    """Read the content of a file, retrying on transient Pebble errors.

    Args:
        path: The file path to read.

    Returns:
        The file content as a string.

    Raises:
        PebbleConnectionError: If the remote container cannot be reached
            after retries.
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be accessed.
    """
    return with_pebble_retry(lambda: path.read_text())


def _write_text_with_retry(path: pathops.LocalPath, content: str, mode: int) -> None:
    """Write text to a file, retrying on transient Pebble errors.

    Args:
        path: The file path to write to.
        content: The text content to write.
        mode: File permission mode to apply (e.g. 0o600).

    Raises:
        PebbleConnectionError: If the remote container cannot be reached
            after retries.
        PermissionError: If the file cannot be written.
        NotADirectoryError: If the parent path is invalid.
    """
    with_pebble_retry(lambda: path.write_text(content, mode=mode))


def _mkdir_with_retry(path: pathops.LocalPath) -> None:
    """Create a directory, retrying on transient Pebble errors.

    Args:
        path: The directory path to create.

    Raises:
        PebbleConnectionError: If the remote container cannot be reached
            after retries.
        PermissionError: If the directory cannot be created.
    """
    with_pebble_retry(lambda: path.mkdir(parents=True, exist_ok=True))
