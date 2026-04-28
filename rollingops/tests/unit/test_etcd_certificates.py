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
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

from typing import Any

from tests.unit.conftest import VALID_CA_CERT_PEM, VALID_CLIENT_CERT_PEM, VALID_CLIENT_KEY_PEM

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    PrivateKey,
)
from charmlibs.rollingops._etcd._models import SharedCertificate


def make_shared_certificate() -> SharedCertificate:
    return SharedCertificate(
        certificate=Certificate.from_string(VALID_CLIENT_CERT_PEM),
        key=PrivateKey.from_string(VALID_CLIENT_KEY_PEM),
        ca=Certificate.from_string(VALID_CA_CERT_PEM),
    )


def test_make_shared_certificate_is_valid():
    Certificate.from_string(VALID_CA_CERT_PEM)
    PrivateKey.from_string(VALID_CLIENT_KEY_PEM)
    Certificate.from_string(VALID_CLIENT_CERT_PEM)


def test_certificates_manager_exists_returns_false_when_no_files(
    temp_certificates: Any,
) -> None:
    assert temp_certificates._exists() is False


def test_certificates_manager_exists_returns_false_when_cert_does_not_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.key_path.write_text('client-key')

    assert temp_certificates._exists() is False


def test_certificates_manager_exists_returns_false_when_key_does_not_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.cert_path.write_text('client-cert')

    assert temp_certificates._exists() is False


def test_certificates_manager_exists_returns_true_when_all_files_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.key_path.write_text('client-key')
    temp_certificates.cert_path.write_text('client-cert')
    temp_certificates.ca_path.write_text('ca-cert')

    assert temp_certificates._exists() is True


def test_certificates_manager_persist_client_cert_and_key_writes_files(
    temp_certificates: Any,
) -> None:
    shared_certificate = make_shared_certificate()
    temp_certificates.persist_client_cert_key_and_ca(shared_certificate)

    assert temp_certificates.cert_path.read_text() == shared_certificate.certificate.raw
    assert temp_certificates.key_path.read_text() == shared_certificate.key.raw
    assert temp_certificates.ca_path.read_text() == shared_certificate.ca.raw


def test_certificates_manager_has_client_cert_and_key_returns_false_when_files_missing(
    temp_certificates: Any,
) -> None:
    shared_certificate = make_shared_certificate()
    assert temp_certificates._has_client_cert_key_and_ca(shared_certificate) is False


def test_certificates_manager_has_client_cert_and_key_returns_true_when_material_matches(
    temp_certificates: Any,
) -> None:
    temp_certificates.cert_path.write_text(VALID_CLIENT_CERT_PEM)
    temp_certificates.key_path.write_text(VALID_CLIENT_KEY_PEM)
    temp_certificates.ca_path.write_text(VALID_CA_CERT_PEM)

    shared_certificate = make_shared_certificate()
    assert temp_certificates._has_client_cert_key_and_ca(shared_certificate) is True


def test_certificates_manager_has_client_cert_and_key_returns_false_when_material_differs(
    temp_certificates: Any,
) -> None:
    temp_certificates.cert_path.write_text(VALID_CLIENT_CERT_PEM)
    temp_certificates.key_path.write_text(VALID_CLIENT_KEY_PEM)
    temp_certificates.ca_path.write_text(VALID_CA_CERT_PEM)

    other_shared_certificate = SharedCertificate(
        certificate=Certificate.from_string(VALID_CA_CERT_PEM),
        key=PrivateKey.from_string(VALID_CLIENT_KEY_PEM),
        ca=Certificate.from_string(VALID_CLIENT_CERT_PEM),
    )
    assert temp_certificates._has_client_cert_key_and_ca(other_shared_certificate) is False


def test_certificates_manager_generate_does_nothing_when_files_already_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.cert_path.write_text(VALID_CLIENT_CERT_PEM)
    temp_certificates.key_path.write_text(VALID_CLIENT_KEY_PEM)
    temp_certificates.ca_path.write_text(VALID_CA_CERT_PEM)
    old_certificates = make_shared_certificate()

    new_certificates = temp_certificates.generate(model_uuid='model', app_name='unit-1')

    written = SharedCertificate.from_strings(
        certificate=temp_certificates.cert_path.read_text(),
        key=temp_certificates.key_path.read_text(),
        ca=temp_certificates.ca_path.read_text(),
    )
    assert written == old_certificates

    assert new_certificates == old_certificates


def test_certificates_manager_generate_creates_all_files(
    temp_certificates: Any,
) -> None:
    shared = temp_certificates.generate(model_uuid='model', app_name='unit-1')
    assert temp_certificates._exists() is True

    assert temp_certificates.ca_path.read_text().startswith('-----BEGIN CERTIFICATE-----')
    assert temp_certificates.key_path.read_text().startswith('-----BEGIN RSA PRIVATE KEY-----')
    assert temp_certificates.cert_path.read_text().startswith('-----BEGIN CERTIFICATE-----')

    assert temp_certificates.ca_path.read_text() == shared.ca.raw
    assert temp_certificates.key_path.read_text() == shared.key.raw
    assert temp_certificates.cert_path.read_text() == shared.certificate.raw
