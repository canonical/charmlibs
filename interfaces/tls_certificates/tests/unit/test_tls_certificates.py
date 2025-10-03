#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import uuid
from datetime import datetime, timedelta, timezone
from ipaddress import IPv6Address

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key, pkcs12

import certificate_validation
from certificates import (
    generate_private_key as generate_private_key_helper,
)
from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateRequestAttributes,
    CertificateSigningRequest,
    PrivateKey,
    calculate_relative_datetime,
    chain_has_valid_order,
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)


def validate_induced_data_from_pfx_is_equal_to_initial_data(
    pfx_file: bytes,
    password: str,
    initial_certificate: bytes,
    initial_private_key: bytes,
):
    (
        induced_private_key_object,
        induced_certificate_object,
        _,
    ) = pkcs12.load_key_and_certificates(pfx_file, password.encode())
    assert induced_private_key_object
    assert induced_certificate_object
    initial_private_key_object = load_pem_private_key(
        initial_private_key,
        password=None,
    )
    assert initial_private_key_object
    induced_private_key = induced_private_key_object.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    initial_public_key_object = initial_private_key_object.public_key()
    initial_public_key = initial_public_key_object.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.PKCS1,
    )
    induced_public_key_object = induced_private_key_object.public_key()
    induced_public_key = induced_public_key_object.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.PKCS1,
    )
    induced_certificate = induced_certificate_object.public_bytes(
        encoding=serialization.Encoding.PEM
    )

    assert initial_public_key == induced_public_key
    assert induced_certificate == initial_certificate
    assert initial_private_key == induced_private_key


def test_given_no_password_when_generate_private_key_then_key_is_generated_and_loadable():
    private_key = generate_private_key()

    load_pem_private_key(data=str(private_key).encode(), password=None)


def test_given_key_size_provided_when_generate_private_key_then_private_key_is_generated():
    key_size = 2234

    private_key = generate_private_key(key_size=key_size)

    private_key_object = serialization.load_pem_private_key(
        str(private_key).encode(), password=None
    )
    assert isinstance(private_key_object, rsa.RSAPrivateKeyWithSerialization)
    assert private_key_object.key_size == key_size


# Generate CSR


def test_given_subject_and_private_key_when_generate_csr_then_csr_is_generated_with_provided_subject():
    common_name = "whatever"
    private_key = PrivateKey(raw=generate_private_key_helper())

    csr = generate_csr(private_key=private_key, common_name=common_name)

    csr_object = x509.load_pem_x509_csr(data=str(csr).encode())
    subject_list = list(csr_object.subject)  # type: ignore
    assert len(subject_list) == 2  # type: ignore
    assert common_name == subject_list[0].value  # type: ignore
    uuid.UUID(str(subject_list[1].value))  # type: ignore


def test_given_unique_id_set_to_false_when_generate_csr_then_csr_is_generated_without_unique_id():
    private_key = PrivateKey(raw=generate_private_key_helper())
    common_name = "whatever subject"

    csr = generate_csr(
        private_key=private_key, common_name=common_name, add_unique_id_to_subject_name=False
    )

    csr_object = x509.load_pem_x509_csr(data=str(csr).encode())
    subject_list = list(csr_object.subject)  # type: ignore
    assert common_name == subject_list[0].value  # type: ignore


def test_given_localization_is_specified_when_generate_csr_then_csr_contains_localization():
    private_key = generate_private_key()

    csr = generate_csr(
        private_key=private_key,
        common_name="my.demo.server",
        sans_dns=frozenset(["my.demo.server"]),
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )

    csr_object = x509.load_pem_x509_csr(str(csr).encode())
    assert csr_object.subject.get_attributes_for_oid(x509.NameOID.COUNTRY_NAME)[0].value == "CA"
    assert (
        csr_object.subject.get_attributes_for_oid(x509.NameOID.STATE_OR_PROVINCE_NAME)[0].value
        == "Quebec"
    )
    assert (
        csr_object.subject.get_attributes_for_oid(x509.NameOID.LOCALITY_NAME)[0].value
        == "Montreal"
    )


def test_given_ipv6_sans_when_generate_csr_then_csr_contains_ipv6_sans():
    private_key = generate_private_key()

    csr = generate_csr(
        private_key=private_key,
        common_name="my.demo.server",
        sans_dns=frozenset(["my.demo.server"]),
        sans_ip=frozenset(["2001:db8::1", "2001:db8::2"]),
    )

    csr_object = x509.load_pem_x509_csr(str(csr).encode())
    sans = csr_object.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    sans_ip = sans.get_values_for_type(x509.IPAddress)
    assert len(sans_ip) == 2
    assert IPv6Address("2001:db8::1") in sans_ip
    assert IPv6Address("2001:db8::2") in sans_ip


def test_given_certificate_request_attributes_when_generate_csr_then_csr_is_generated_correctly():
    private_key = generate_private_key()

    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        sans_ip=frozenset(["1.2.3.4"]),
        sans_oid=frozenset(["1.2.3.4"]),
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )
    assert csr.common_name == "example.com"
    assert csr.sans_dns == frozenset(["example.com"])
    assert csr.sans_ip == frozenset(["1.2.3.4"])
    assert csr.sans_oid is not None
    assert len(csr.sans_oid) == 1
    oid = next(iter(csr.sans_oid))
    assert "1.2.3.4" in str(oid)
    assert csr.email_address == "banana@gmail.com"
    assert csr.organization == "Example"
    assert csr.organizational_unit == "Example Unit"
    assert csr.country_name == "CA"
    assert csr.state_or_province_name == "Quebec"
    assert csr.locality_name == "Montreal"


# Generate CA
def test_given_email_address_when_generate_ca_then_san_is_present():
    # 4.1.2.6
    # Conforming implementations generating new certificates with
    # electronic mail addresses MUST use the rfc822Name in the subject
    # alternative name extension (Section 4.2.1.6) to describe such
    # identities.  Simultaneous inclusion of the emailAddress attribute in
    # the subject distinguished name to support legacy implementations is
    # deprecated but permitted.

    private_key = PrivateKey(raw=generate_private_key_helper())

    ca_certificate = generate_ca(
        private_key=private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )

    ca = x509.load_pem_x509_certificate(str(ca_certificate).encode())
    sans = ca.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    rfc822names = sans.get_values_for_type(x509.RFC822Name)

    assert "banana@gmail.com" in rfc822names

    assert not certificate_validation.get_violations(ca_certificate)


def test_given_no_sans_when_generate_ca_then_ca_is_generated_without_sans():
    private_key = PrivateKey(raw=generate_private_key_helper())

    ca_certificate = generate_ca(
        private_key=private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )

    ca = x509.load_pem_x509_certificate(str(ca_certificate).encode())
    with pytest.raises(x509.ExtensionNotFound):
        ca.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert not certificate_validation.get_violations(ca_certificate)


def test_given_ca_certificate_attributes_when_generate_ca_then_ca_is_generated_correctly():
    private_key = PrivateKey(raw=generate_private_key_helper())

    ca_certificate = generate_ca(
        private_key=private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        sans_dns=frozenset(["certifier.example.com"]),
        sans_ip=frozenset(["1.2.3.4"]),
        sans_oid=frozenset(["1.2.3.4"]),
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )

    assert ca_certificate.common_name == "certifier.example.com"
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=365)
    assert ca_certificate.expiry_time
    assert abs(ca_certificate.expiry_time - expected_expiry) <= timedelta(seconds=1)
    assert ca_certificate.email_address == "banana@gmail.com"
    assert ca_certificate.organization == "Example"
    assert ca_certificate.organizational_unit == "Example Unit"
    assert ca_certificate.country_name == "CA"
    assert ca_certificate.state_or_province_name == "Quebec"
    assert ca_certificate.locality_name == "Montreal"
    assert ca_certificate.sans_dns == frozenset(["certifier.example.com"])
    assert ca_certificate.sans_ip == frozenset(["1.2.3.4"])
    assert ca_certificate.sans_oid is not None
    assert len(ca_certificate.sans_oid) == 1
    oid = next(iter(ca_certificate.sans_oid))
    assert "1.2.3.4" in str(oid)

    assert not certificate_validation.get_violations(ca_certificate)


# Generate Certificate


def test_given_csr_when_generate_certificate_then_certificate_generated_with_requested_attributes():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        locality_name="wherever",
    )
    ca_private_key = generate_private_key()
    ca_certificate = generate_ca(
        private_key=ca_private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        email_address="my@email.com",
        sans_dns=frozenset(["certifier.example.com"]),
    )

    certificate = generate_certificate(
        csr=csr,
        ca=ca_certificate,
        ca_private_key=ca_private_key,
        validity=timedelta(days=200),
        is_ca=False,
    )

    assert certificate.common_name == "example.com"
    assert certificate.is_ca is False
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=200)
    assert certificate.expiry_time
    assert abs(certificate.expiry_time - expected_expiry) <= timedelta(seconds=1)
    assert certificate.sans_dns == frozenset(["example.com"])
    assert certificate.sans_ip == frozenset()
    assert certificate.sans_oid == frozenset()
    assert certificate.email_address is None
    assert certificate.country_name is None
    assert certificate.locality_name == "wherever"

    assert not certificate_validation.get_violations(ca_certificate)
    assert not certificate_validation.get_violations(certificate)


def test_given_csr_for_ca_when_generate_certificate_then_certificate_generated_with_requested_attributes():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        locality_name="wherever",
    )
    ca_private_key = generate_private_key()
    ca_certificate = generate_ca(
        private_key=ca_private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        sans_dns=frozenset(["certifier.example.com"]),
    )

    certificate = generate_certificate(
        csr=csr,
        ca=ca_certificate,
        ca_private_key=ca_private_key,
        validity=timedelta(days=200),
        is_ca=True,
    )

    assert certificate.common_name == "example.com"
    assert certificate.is_ca is True
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=200)
    assert certificate.expiry_time
    assert abs(certificate.expiry_time - expected_expiry) <= timedelta(seconds=1)
    assert certificate.sans_dns == frozenset(["example.com"])
    assert certificate.sans_ip == frozenset()
    assert certificate.sans_oid == frozenset()
    assert certificate.email_address is None
    assert certificate.country_name is None
    assert certificate.locality_name == "wherever"

    assert not certificate_validation.get_violations(ca_certificate)
    assert not certificate_validation.get_violations(certificate)


def test_given_csr_without_email_or_sans_when_generate_certificate_then_certificate_generated_without_sans():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
    )
    ca_private_key = generate_private_key()
    ca_certificate = generate_ca(
        private_key=ca_private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        sans_dns=frozenset(["certifier.example.com"]),
    )
    certificate = generate_certificate(
        csr=csr,
        ca=ca_certificate,
        ca_private_key=ca_private_key,
        validity=timedelta(days=200),
        is_ca=False,
    )

    certificate_object = x509.load_pem_x509_certificate(str(certificate).encode())
    with pytest.raises(x509.ExtensionNotFound):
        certificate_object.extensions.get_extension_for_class(x509.SubjectAlternativeName)

    assert not certificate_validation.get_violations(certificate)


# from_string and from_csr


def test_given_csr_string_when_from_string_then_certificate_signing_request_is_created_correctly():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        sans_ip=frozenset(["1.2.3.4"]),
        sans_oid=frozenset(["1.2.3.4"]),
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
        add_unique_id_to_subject_name=False,
    )
    csr_from_string = CertificateSigningRequest.from_string(str(csr))
    assert csr_from_string.common_name == "example.com"
    assert csr_from_string.sans_dns == frozenset(["example.com"])
    assert csr_from_string.sans_ip == frozenset(["1.2.3.4"])
    assert csr_from_string.sans_oid == frozenset(["1.2.3.4"])
    assert csr_from_string.email_address == "banana@gmail.com"
    assert csr_from_string.organization == "Example"
    assert csr_from_string.organizational_unit == "Example Unit"
    assert csr_from_string.country_name == "CA"
    assert csr_from_string.state_or_province_name == "Quebec"
    assert csr_from_string.locality_name == "Montreal"
    assert not csr_from_string.has_unique_identifier


def test_given_certificate_signin_request_when_from_csr_then_attributes_are_correctly_parsed():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        sans_ip=frozenset(["1.2.3.4"]),
        sans_oid=frozenset(["1.2.3.4"]),
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )
    csr_from_string = CertificateSigningRequest.from_string(str(csr))
    attributes = CertificateRequestAttributes.from_csr(csr_from_string, is_ca=False)
    assert attributes.common_name == "example.com"
    assert attributes.sans_dns == frozenset(["example.com"])
    assert attributes.sans_ip == frozenset(["1.2.3.4"])
    assert attributes.sans_oid == frozenset(["1.2.3.4"])
    assert attributes.email_address == "banana@gmail.com"
    assert attributes.organization == "Example"
    assert attributes.organizational_unit == "Example Unit"
    assert attributes.country_name == "CA"
    assert attributes.state_or_province_name == "Quebec"
    assert attributes.locality_name == "Montreal"


def test_given_certificate_string_when_from_string_then_certificate_is_created_correctly():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        sans_ip=frozenset(["1.2.3.4"]),
        sans_oid=frozenset(["1.2.3.4"]),
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )
    ca_private_key = generate_private_key()
    ca_certificate = generate_ca(
        private_key=ca_private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        sans_dns=frozenset(["certifier.example.com"]),
    )
    certificate = generate_certificate(
        csr=csr,
        ca=ca_certificate,
        ca_private_key=ca_private_key,
        validity=timedelta(days=200),
        is_ca=False,
    )
    certificate_from_string = Certificate.from_string(str(certificate))
    assert certificate_from_string.common_name == "example.com"
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=200)  # FIXME: Relies on time
    assert abs(certificate_from_string.expiry_time - expected_expiry) <= timedelta(seconds=2)
    expected_validity_start_time = datetime.now(timezone.utc)  # FIXME: Relies on time
    assert abs(
        certificate_from_string.validity_start_time - expected_validity_start_time
    ) <= timedelta(seconds=2)
    assert certificate_from_string.sans_dns == frozenset(["example.com"])
    assert certificate_from_string.sans_ip == frozenset(["1.2.3.4"])
    assert certificate_from_string.sans_oid is not None
    assert len(certificate_from_string.sans_oid) == 1
    oid = next(iter(certificate_from_string.sans_oid))
    assert "1.2.3.4" in str(oid)
    assert certificate_from_string.email_address == "banana@gmail.com"
    assert certificate_from_string.organization == "Example"
    assert certificate_from_string.organizational_unit == "Example Unit"
    assert certificate_from_string.country_name == "CA"
    assert certificate_from_string.state_or_province_name == "Quebec"
    assert certificate_from_string.locality_name == "Montreal"
    assert certificate_from_string.is_ca is False

    assert not certificate_validation.get_violations(ca_certificate)
    assert not certificate_validation.get_violations(certificate)


def test_given_datetime_and_fraction_when_calculate_relative_datetime_then_datetime_is_returned():
    now = datetime.now(timezone.utc)
    target_time = now + timedelta(days=10)
    fraction = 0.5
    relative_datetime = calculate_relative_datetime(target_time, fraction)
    expected_relative_datetime = now + timedelta(days=5)
    assert abs((relative_datetime - expected_relative_datetime).total_seconds()) <= 60


def test_given_chain_with_valid_order_when_chain_has_valid_order_then_returns_true():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        sans_ip=frozenset(["1.2.3.4"]),
        sans_oid=frozenset(["1.2.3.4"]),
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )
    ca_private_key = generate_private_key()
    ca_certificate = generate_ca(
        private_key=ca_private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        sans_dns=frozenset(["certifier.example.com"]),
    )
    certificate = generate_certificate(
        csr=csr,
        ca=ca_certificate,
        ca_private_key=ca_private_key,
        validity=timedelta(days=200),
        is_ca=False,
    )
    chain = [str(certificate), str(ca_certificate)]
    assert chain_has_valid_order(chain)


def test_given_chain_with_invalid_order_when_chain_has_valid_order_then_returns_false():
    private_key = generate_private_key()
    csr = generate_csr(
        private_key=private_key,
        common_name="example.com",
        sans_dns=frozenset(["example.com"]),
        sans_ip=frozenset(["1.2.3.4"]),
        sans_oid=frozenset(["1.2.3.4"]),
        email_address="banana@gmail.com",
        organization="Example",
        organizational_unit="Example Unit",
        country_name="CA",
        state_or_province_name="Quebec",
        locality_name="Montreal",
    )
    ca_private_key = generate_private_key()
    ca_certificate = generate_ca(
        private_key=ca_private_key,
        validity=timedelta(days=365),
        common_name="certifier.example.com",
        sans_dns=frozenset(["certifier.example.com"]),
    )
    certificate = generate_certificate(
        csr=csr,
        ca=ca_certificate,
        ca_private_key=ca_private_key,
        validity=timedelta(days=200),
        is_ca=False,
    )
    assert not chain_has_valid_order([str(ca_certificate), str(certificate)])
    assert not chain_has_valid_order([str(certificate), "Random string"])
