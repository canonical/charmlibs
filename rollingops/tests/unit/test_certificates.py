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

from charmlibs.rollingops._models import SharedCertificate


def test_certificates_manager_exists_returns_false_when_no_files(
    temp_certificates: Any,
) -> None:
    assert temp_certificates._exists() is False


def test_certificates_manager_exists_returns_false_when_cert_does_not_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.CLIENT_KEY_PATH.write_text('client-key')

    assert temp_certificates._exists() is False


def test_certificates_manager_exists_returns_false_when_key_does_not_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.CLIENT_CERT_PATH.write_text('client-cert')

    assert temp_certificates._exists() is False


def test_certificates_manager_exists_returns_true_when_all_files_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.CLIENT_KEY_PATH.write_text('client-key')
    temp_certificates.CLIENT_CERT_PATH.write_text('client-cert')
    temp_certificates.CA_CERT_PATH.write_text('ca-cert')

    assert temp_certificates._exists() is True


def test_certificates_manager_persist_client_cert_and_key_writes_files(
    temp_certificates: Any,
) -> None:
    shared_certificate = SharedCertificate('cert-pem', 'key-pem', 'ca-pem')
    temp_certificates.persist_client_cert_key_and_ca(shared_certificate)

    assert temp_certificates.CLIENT_CERT_PATH.read_text() == 'cert-pem'
    assert temp_certificates.CLIENT_KEY_PATH.read_text() == 'key-pem'


def test_certificates_manager_has_client_cert_and_key_returns_false_when_files_missing(
    temp_certificates: Any,
) -> None:
    shared_certificate = SharedCertificate('cert-pem', 'key-pem', 'ca-pem')
    assert temp_certificates._has_client_cert_key_and_ca(shared_certificate) is False


def test_certificates_manager_has_client_cert_and_key_returns_true_when_material_matches(
    temp_certificates: Any,
) -> None:
    temp_certificates.CLIENT_CERT_PATH.write_text('cert-pem')
    temp_certificates.CLIENT_KEY_PATH.write_text('key-pem')
    temp_certificates.CA_CERT_PATH.write_text('ca-pem')

    shared_certificate = SharedCertificate('cert-pem', 'key-pem', 'ca-pem')
    assert temp_certificates._has_client_cert_key_and_ca(shared_certificate) is True


def test_certificates_manager_has_client_cert_and_key_returns_false_when_material_differs(
    temp_certificates: Any,
) -> None:
    temp_certificates.CLIENT_CERT_PATH.write_text('cert-pem')
    temp_certificates.CLIENT_KEY_PATH.write_text('key-pem')
    temp_certificates.CA_CERT_PATH.write_text('ca-pem')

    shared_certificate1 = SharedCertificate('other-cert', 'key-pem', 'ca-pem')
    shared_certificate2 = SharedCertificate('cert-pem', 'other-key', 'ca-pem')
    shared_certificate3 = SharedCertificate('cert-pem', 'key-pem', 'other-pem')
    assert temp_certificates._has_client_cert_key_and_ca(shared_certificate1) is False
    assert temp_certificates._has_client_cert_key_and_ca(shared_certificate2) is False
    assert temp_certificates._has_client_cert_key_and_ca(shared_certificate3) is False


def test_certificates_manager_generate_does_nothing_when_files_already_exist(
    temp_certificates: Any,
) -> None:
    temp_certificates.CA_CERT_PATH.write_text('existing-ca-cert')
    temp_certificates.CLIENT_KEY_PATH.write_text('existing-client-key')
    temp_certificates.CLIENT_CERT_PATH.write_text('existing-client-cert')

    shared = temp_certificates.generate(common_name='unit-1')

    assert temp_certificates.CA_CERT_PATH.read_text() == 'existing-ca-cert'
    assert temp_certificates.CLIENT_KEY_PATH.read_text() == 'existing-client-key'
    assert temp_certificates.CLIENT_CERT_PATH.read_text() == 'existing-client-cert'

    assert shared.ca == 'existing-ca-cert'
    assert shared.key == 'existing-client-key'
    assert shared.certificate == 'existing-client-cert'


def test_certificates_manager_generate_creates_all_files(
    temp_certificates: Any,
) -> None:
    shared = temp_certificates.generate(common_name='unit-1')
    assert temp_certificates._exists() is True

    assert temp_certificates.CA_CERT_PATH.read_text().startswith('-----BEGIN CERTIFICATE-----')
    assert temp_certificates.CLIENT_KEY_PATH.read_text().startswith(
        '-----BEGIN RSA PRIVATE KEY-----'
    )
    assert temp_certificates.CLIENT_CERT_PATH.read_text().startswith('-----BEGIN CERTIFICATE-----')

    assert temp_certificates.CA_CERT_PATH.read_text() == shared.ca
    assert temp_certificates.CLIENT_KEY_PATH.read_text() == shared.key
    assert temp_certificates.CLIENT_CERT_PATH.read_text() == shared.certificate
