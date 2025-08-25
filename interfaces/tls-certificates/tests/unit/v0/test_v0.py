#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest
from unittest.mock import Mock, PropertyMock, call, patch

import pytest

from charmlibs.interfaces.tls_certificates.v0 import (
    Cert,
    TLSCertificatesProvides,
    TLSCertificatesRequires,
)

PROVIDER_UNIT_NAME = "whatever provider unit name"
REQUIRER_UNIT_NAME = "whatever requirer unit name"
CHARM_LIB_PATH = "charmlibs.interfaces.tls_certificates.v0"


class LeaderUnitMock:
    def __init__(self, name):
        self.name = name

    @staticmethod
    def is_leader():
        return True


class NonLeaderUnitMock:
    def __init__(self, name):
        self.name = name

    @staticmethod
    def is_leader():
        return False


def _load_relation_data(raw_relation_data: dict) -> dict:
    certificate_data = {}
    for key in raw_relation_data:
        try:
            certificate_data[key] = json.loads(raw_relation_data[key])
        except json.decoder.JSONDecodeError:
            certificate_data[key] = raw_relation_data[key]
    return certificate_data


class TestTLSCertificatesProvides(unittest.TestCase):
    def setUp(self):
        class MockRelation:
            def relation_changed(self):
                pass

        relationship_name = "certificates"
        charm = Mock()
        charm.on = {"certificates": MockRelation()}
        self.tls_relation_provides = TLSCertificatesProvides(
            charm=charm, relationship_name=relationship_name
        )
        self.charm = charm
        self.provider_unit = LeaderUnitMock(name=PROVIDER_UNIT_NAME)
        self.requirer_unit = NonLeaderUnitMock(name=REQUIRER_UNIT_NAME)
        self.charm.framework.model.unit = self.provider_unit

    @patch(
        f"{CHARM_LIB_PATH}.CertificatesProviderCharmEvents.certificate_request",
        new_callable=PropertyMock,
    )
    def test_given_common_name_is_missing_from_relation_data_when_relation_changed_then_no_certificate_request_is_made(  # noqa: E501
        self, patch_emit
    ):
        certificate_requests = [
            {
                "sans": json.dumps(["whatever sans"]),
            }
        ]
        event = Mock()
        event.relation.data = {
            self.requirer_unit: {"cert_requests": json.dumps(certificate_requests)},
            self.provider_unit: {},
        }
        event.unit = self.requirer_unit

        self.tls_relation_provides._on_relation_changed(event)

        patch_emit.assert_not_called()

    @patch(
        f"{CHARM_LIB_PATH}.CertificatesProviderCharmEvents.certificate_request",
        new_callable=PropertyMock,
    )
    def test_given_invalid_cert_requests_in_relation_data_when_relation_changed_then_no_certificate_request_is_made(  # noqa: E501
        self, patch_emit
    ):
        invalid_cert_request_content = "invalid format"
        event = Mock()
        event.relation.data = {
            self.requirer_unit: {
                "common_name": "whatever common name",
                "cert_requests": invalid_cert_request_content,
            },
            self.provider_unit: {},
        }
        event.unit = self.requirer_unit

        self.tls_relation_provides._on_relation_changed(event)

        patch_emit.assert_not_called()

    @patch(
        f"{CHARM_LIB_PATH}.CertificatesProviderCharmEvents.certificate_request",
        new_callable=PropertyMock,
    )
    def test_given_cert_requests_in_relation_data_when_relation_changed_then_certificate_request_event_is_emitted_for_each_request(  # noqa: E501
        self, patch_emit
    ):
        blou = Mock()
        patch_emit.emit = blou
        relation_id = 1
        cert_request_1_common_name = "cert request 1 common name"
        cert_request_2_common_name = "cert request 2 common name"
        client_cert_request_1_common_name = "client cert request 1 common name"
        client_cert_request_2_common_name = "client cert request 2 common name"
        cert_requests = [
            {"common_name": cert_request_1_common_name},
            {"common_name": cert_request_2_common_name},
        ]
        client_cert_requests = [
            {"common_name": client_cert_request_1_common_name},
            {"common_name": client_cert_request_2_common_name},
        ]
        event = Mock()
        event.relation.data = {
            self.requirer_unit: {
                "cert_requests": json.dumps(cert_requests),
                "client_cert_requests": json.dumps(client_cert_requests),
            },
            self.provider_unit: {},
        }
        event.relation.id = relation_id
        event.unit = self.requirer_unit

        self.tls_relation_provides._on_relation_changed(event)

        calls = [
            call().emit(
                common_name=cert_request_1_common_name,
                sans=None,
                cert_type="server",
                relation_id=relation_id,
            ),
            call().emit(
                common_name=cert_request_2_common_name,
                sans=None,
                cert_type="server",
                relation_id=relation_id,
            ),
            call().emit(
                common_name=client_cert_request_1_common_name,
                sans=None,
                cert_type="client",
                relation_id=relation_id,
            ),
            call().emit(
                common_name=client_cert_request_2_common_name,
                sans=None,
                cert_type="client",
                relation_id=relation_id,
            ),
        ]

        patch_emit.assert_has_calls(calls, any_order=True)

    def test_given_certificate_when_set_relation_certificate_then_cert_is_added_to_relation_data(
        self,
    ):
        class Relation:
            data: dict = {self.provider_unit: {}, self.requirer_unit: {}}

        common_name = "whatever common name"
        cert = "whatever certificate"
        private_key = "whatever private key"
        certificate = Cert(
            cert=cert,
            key=private_key,
            ca="whatever ca",
            common_name=common_name,
        )
        relation_id = 1
        relation = Relation()
        self.charm.framework.model.get_relation.return_value = relation

        self.tls_relation_provides.set_relation_certificate(
            certificate=certificate, relation_id=relation_id
        )

        relation_data = _load_relation_data(relation.data[self.provider_unit])

        expected_relation_data = {"cert": cert, "key": private_key}
        self.assertEqual(expected_relation_data, relation_data[common_name])

    def test_given_certificate_when_set_relation_certificate_then_ca_is_added_to_relation_data(
        self,
    ):
        class Relation:
            data: dict = {self.provider_unit: {}, self.requirer_unit: {}}

        common_name = "whatever common name"
        cert = "whatever certificate"
        private_key = "whatever private key"
        certificate = Cert(
            cert=cert,
            key=private_key,
            ca="whatever ca",
            common_name=common_name,
        )
        relation_id = 1
        relation = Relation()
        self.charm.framework.model.get_relation.return_value = relation

        self.tls_relation_provides.set_relation_certificate(
            certificate=certificate, relation_id=relation_id
        )

        relation_data = _load_relation_data(relation.data[self.provider_unit])

        self.assertEqual(certificate["ca"], relation_data["ca"])


class TestTLSCertificatesRequires(unittest.TestCase):
    def setUp(self):
        class CharmOnMock:
            certificates = Mock()
            certificate_request = Mock()

            def __getitem__(self, key):
                return getattr(self, key)

        charm = Mock()
        charm.on = CharmOnMock()
        relationship_name = "certificates"
        self.tls_certificate_requires = TLSCertificatesRequires(
            charm=charm, relationship_name=relationship_name
        )
        self.charm = charm
        self.provider_unit = LeaderUnitMock(name=PROVIDER_UNIT_NAME)
        self.requirer_unit = NonLeaderUnitMock(name=REQUIRER_UNIT_NAME)
        self.charm.framework.model.unit = self.requirer_unit

    def test_given_client_when_request_certificate_then_client_cert_request_is_added_to_relation_data(  # noqa: E501
        self,
    ):
        class Relation:
            data: dict = {self.provider_unit: {}, self.requirer_unit: {}}

        common_name = "whatever common name"
        relation = Relation()
        self.charm.framework.model.get_relation.return_value = relation

        self.tls_certificate_requires.request_certificate(
            cert_type="client",
            common_name=common_name,
        )

        assert "client_cert_requests" in relation.data[self.requirer_unit]
        client_cert_requests = json.loads(
            relation.data[self.requirer_unit]["client_cert_requests"]
        )
        expected_client_cert_requests = [{"common_name": common_name, "sans": []}]
        self.assertEqual(expected_client_cert_requests, client_cert_requests)

    def test_given_no_relation_when_request_certificate_then_runtime_error_is_raised(self):
        self.charm.framework.model.get_relation.return_value = None

        with pytest.raises(RuntimeError):
            self.tls_certificate_requires.request_certificate(
                cert_type="client", common_name="whatever common name"
            )

    @patch(
        f"{CHARM_LIB_PATH}.CertificatesRequirerCharmEvents.certificate_available",
        new_callable=PropertyMock,
    )
    def test_given_non_valid_relation_data_when_on_relation_changed_then_certificate_available_event_is_not_emitted(
        self, patch_emit
    ):
        event = Mock()
        bad_relation_data = [
            {
                "common_name": "aaa",  # key, cert and ca are missing
            }
        ]
        event.relation.data = {
            self.requirer_unit: {},
            self.provider_unit: {"certificates": json.dumps(bad_relation_data)},
        }
        event.unit = self.provider_unit
        self.tls_certificate_requires._on_relation_changed(event)

        patch_emit.assert_not_called()

    @patch(
        f"{CHARM_LIB_PATH}.CertificatesRequirerCharmEvents.certificate_available",
        new_callable=PropertyMock,
    )
    def test_given_valid_relation_data_and_unit_is_not_leader_when_on_relation_changed_then_certificate_available_event_is_emitted(  # noqa: E501
        self, patch_emit
    ):
        event = Mock()
        ca = "whatever ca"
        cert = "whatever cert"
        private_key = "whatever private key"
        common_name = "whatever.com"
        relation_data = {
            "ca": ca,
            "chain": ca,
            common_name: json.dumps({"cert": cert, "key": private_key}),
            "whatever key": "whatever value",
            "unit_name": "whatever unit name",
        }
        event.unit = self.provider_unit
        event.relation.data = {
            self.requirer_unit: {},
            self.provider_unit: relation_data,
        }

        self.tls_certificate_requires._on_relation_changed(event)

        calls = [
            call().emit(
                certificate_data=Cert(cert=cert, key=private_key, ca=ca, common_name=common_name)
            )
        ]
        patch_emit.assert_has_calls(calls, any_order=True)

    @patch(
        f"{CHARM_LIB_PATH}.CertificatesRequirerCharmEvents.certificate_available",
        new_callable=PropertyMock,
    )
    def test_given_valid_relation_data_and_unit_is_leader_when_on_relation_changed_then_certificate_available_event_is_emitted(  # noqa: E501
        self, patch_emit
    ):
        event = Mock()
        ca = "whatever ca"
        cert = "whatever cert"
        private_key = "whatever private key"
        common_name = "whatever.com"
        relation_data = {
            "ca": ca,
            "chain": ca,
            common_name: json.dumps({"cert": cert, "key": private_key}),
            "whatever key": "whatever value",
            "unit_name": "whatever unit name",
        }
        event.unit = self.provider_unit
        event.relation.data = {
            self.requirer_unit: {},
            self.provider_unit: relation_data,
        }
        self.charm.framework.model.unit = LeaderUnitMock(name=PROVIDER_UNIT_NAME)

        self.tls_certificate_requires._on_relation_changed(event)

        calls = [
            call().emit(
                certificate_data=Cert(cert=cert, key=private_key, ca=ca, common_name=common_name)
            )
        ]
        patch_emit.assert_has_calls(calls, any_order=True)
