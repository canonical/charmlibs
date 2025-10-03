# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import uuid
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_private_key(
    key_size: int = 2048,
    public_exponent: int = 65537,
) -> str:
    """Generate a private key.

    Args:
        password (bytes): Password for decrypting the private key
        key_size (int): Key size in bytes
        public_exponent: Public exponent.

    Returns:
        str: Private Key
    """
    private_key = rsa.generate_private_key(
        public_exponent=public_exponent,
        key_size=key_size,
    )
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key_bytes.decode().strip()


def generate_csr(
    private_key: str,
    common_name: str,
    sans: list[str] | None = None,
) -> str:
    """Generate a CSR using private key and subject.

    Args:
        private_key (str): Private key
        common_name (str): CSR common name.
        sans (list): List of subject alternative names

    Returns:
        str: CSR
    """
    signing_key = serialization.load_pem_private_key(private_key.encode(), password=None)
    unique_identifier = uuid.uuid4()
    subject_name = [x509.NameAttribute(x509.NameOID.COMMON_NAME, common_name)]
    subject_name.append(
        x509.NameAttribute(x509.NameOID.X500_UNIQUE_IDENTIFIER, str(unique_identifier))
    )
    csr = x509.CertificateSigningRequestBuilder(subject_name=x509.Name(subject_name))
    if sans:
        csr.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(san) for san in sans]), critical=False
        )
    signed_certificate = csr.sign(signing_key, hashes.SHA256())  # type: ignore[arg-type]
    return signed_certificate.public_bytes(serialization.Encoding.PEM).decode().strip()


def generate_certificate(
    csr: str,
    ca: str,
    ca_key: str,
    validity: timedelta = timedelta(days=365),
    is_ca: bool = False,
) -> str:
    """Generate a TLS certificate based on a CSR.

    Args:
        csr (str): CSR
        ca (str): CA Certificate
        ca_key (str): CA private key
        validity (timedelta): Certificate validity
        is_ca (bool): Is the certificate a CA certificate

    Returns:
        str: Certificate
    """
    csr_object = x509.load_pem_x509_csr(csr.encode())
    csr_subject = csr_object.subject
    csr_common_name = csr_subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    issuer = x509.load_pem_x509_certificate(ca.encode()).issuer
    private_key = serialization.load_pem_private_key(ca_key.encode(), password=None)
    subject = x509.Name([
        x509.NameAttribute(x509.NameOID.COMMON_NAME, csr_common_name),
    ])

    if validity > timedelta(0):
        not_valid_before = datetime.now(timezone.utc)
        not_valid_after = datetime.now(timezone.utc) + validity
    else:
        not_valid_before = datetime.now(timezone.utc) + validity
        not_valid_after = datetime.now(timezone.utc) - validity
    certificate_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(csr_object.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
    )

    if is_ca:
        certificate_builder = certificate_builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )

    certificate_builder._version = x509.Version.v3
    cert = certificate_builder.sign(private_key, hashes.SHA256())  # type: ignore[arg-type]
    return cert.public_bytes(serialization.Encoding.PEM).decode().strip()


def generate_ca(
    private_key: str,
    common_name: str,
    validity: timedelta = timedelta(days=365),
) -> str:
    """Generate a CA Certificate.

    Args:
        private_key (bytes): Private key
        private_key_password (bytes): Private key password
        common_name (str): Certificate common name.
        validity (int): Certificate validity time (in days)
        country (str): Certificate Issuing country

    Returns:
        str: CA Certificate
    """
    private_key_object = serialization.load_pem_private_key(private_key.encode(), password=None)
    subject = issuer = x509.Name([
        x509.NameAttribute(x509.NameOID.COMMON_NAME, common_name),
    ])
    subject_identifier_object = x509.SubjectKeyIdentifier.from_public_key(
        private_key_object.public_key()  # type: ignore[arg-type]
    )
    subject_identifier = key_identifier = subject_identifier_object.public_bytes()

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key_object.public_key())  # type: ignore[arg-type]
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + validity)
        .add_extension(x509.SubjectKeyIdentifier(digest=subject_identifier), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier(
                key_identifier=key_identifier,
                authority_cert_issuer=None,
                authority_cert_serial_number=None,
            ),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(private_key_object, hashes.SHA256())  # type: ignore[arg-type]
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode().strip()
