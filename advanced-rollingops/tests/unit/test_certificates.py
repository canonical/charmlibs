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


def test_certificates_manager_exists_returns_false_when_no_files(temp_cert_manager) -> None:
    assert temp_cert_manager._exists() is False


def test_certificates_manager_exists_returns_false_when_cert_does_not_exist(
    temp_cert_manager,
) -> None:
    temp_cert_manager.CLIENT_KEY.write_text('client-key')

    assert temp_cert_manager._exists() is False


def test_certificates_manager_exists_returns_false_when_key_does_not_exist(
    temp_cert_manager,
) -> None:
    temp_cert_manager.CLIENT_CERT.write_text('client-cert')

    assert temp_cert_manager._exists() is False


def test_certificates_manager_exists_returns_true_when_all_files_exist(temp_cert_manager) -> None:
    temp_cert_manager.CLIENT_KEY.write_text('client-key')
    temp_cert_manager.CLIENT_CERT.write_text('client-cert')
    temp_cert_manager.CA_CERT.write_text('ca-cert')

    assert temp_cert_manager._exists() is True


def test_certificates_manager_persist_client_cert_and_key_writes_files(
    temp_cert_manager,
) -> None:
    temp_cert_manager.persist_client_cert_key_and_ca('cert-pem', 'key-pem', 'ca-pem')

    assert temp_cert_manager.CLIENT_CERT.read_text() == 'cert-pem'
    assert temp_cert_manager.CLIENT_KEY.read_text() == 'key-pem'


def test_certificates_manager_has_client_cert_and_key_returns_false_when_files_missing(
    temp_cert_manager,
) -> None:
    assert temp_cert_manager.has_client_cert_key_and_ca('cert', 'key', 'ca') is False


def test_certificates_manager_has_client_cert_and_key_returns_true_when_material_matches(
    temp_cert_manager,
) -> None:
    temp_cert_manager.CLIENT_CERT.write_text('cert-pem')
    temp_cert_manager.CLIENT_KEY.write_text('key-pem')
    temp_cert_manager.CA_CERT.write_text('ca-pem')

    assert temp_cert_manager.has_client_cert_key_and_ca('cert-pem', 'key-pem', 'ca-pem') is True


def test_certificates_manager_has_client_cert_and_key_returns_false_when_material_differs(
    temp_cert_manager,
) -> None:
    temp_cert_manager.CLIENT_CERT.write_text('cert-pem')
    temp_cert_manager.CLIENT_KEY.write_text('key-pem')
    temp_cert_manager.CA_CERT.write_text('ca-pem')

    assert temp_cert_manager.has_client_cert_key_and_ca('other-cert', 'key-pem', 'ca-pem') is False
    assert temp_cert_manager.has_client_cert_key_and_ca('cert-pem', 'other-key', 'ca-pem') is False
    assert (
        temp_cert_manager.has_client_cert_key_and_ca('cert-pem', 'key-pem', 'other-pem') is False
    )


def test_certificates_manager_generate_does_nothing_when_files_already_exist(
    temp_cert_manager,
) -> None:
    temp_cert_manager.CA_CERT.write_text('existing-ca-cert')
    temp_cert_manager.CLIENT_KEY.write_text('existing-client-key')
    temp_cert_manager.CLIENT_CERT.write_text('existing-client-cert')

    temp_cert_manager.generate(common_name='unit-1')

    assert temp_cert_manager.CA_CERT.read_text() == 'existing-ca-cert'
    assert temp_cert_manager.CLIENT_KEY.read_text() == 'existing-client-key'
    assert temp_cert_manager.CLIENT_CERT.read_text() == 'existing-client-cert'


def test_certificates_manager_generate_creates_all_files(
    temp_cert_manager,
) -> None:
    temp_cert_manager.generate(common_name='unit-1')
    assert temp_cert_manager._exists() is True

    assert temp_cert_manager.CA_CERT.read_text().startswith('-----BEGIN CERTIFICATE-----')
    assert temp_cert_manager.CLIENT_KEY.read_text().startswith('-----BEGIN RSA PRIVATE KEY-----')
    assert temp_cert_manager.CLIENT_CERT.read_text().startswith('-----BEGIN CERTIFICATE-----')
