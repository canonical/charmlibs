# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import datetime
import json
from collections.abc import Iterable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import scenario
import yaml
from cryptography.hazmat.primitives import hashes
from ops import testing
from ops.testing import ActionFailed, Secret

from certificates import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)
from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateAvailableEvent,
    CertificateSigningRequest,
    Mode,
    PrivateKey,
    TLSCertificatesError,
)
from requirer_charm import (
    DummyTLSCertificatesRequirerCharm,
)

BASE_CHARM_DIR = "requirer_charm.DummyTLSCertificatesRequirerCharm"
LIB_DIR = "charmlibs.interfaces.tls_certificates"
LIBID = "afd8c2bccf834997afce12c2706d2ede"

METADATA = yaml.safe_load(
    (Path(__file__).parent / "dummy_requirer_charm" / "charmcraft.yaml").read_text()
)


def get_private_string_key_from_file() -> str:
    return (Path(__file__).parent / "dummy_requirer_charm" / "private_key.pem").read_text()


def get_private_key_from_file() -> PrivateKey:
    return PrivateKey.from_string(get_private_string_key_from_file())


def get_sha256_hex(data: str) -> str:
    """Calculate the hash of the provided data and return the hexadecimal representation."""
    digest = hashes.Hash(hashes.SHA256())
    digest.update(data.encode())
    return digest.finalize().hex()


class TestTLSCertificatesRequiresV4:
    def private_key_secret_exists(self, secrets: Iterable[Secret], label: str) -> bool:
        return any(secret.label == label for secret in secrets)

    def certificate_secret_exists(self, secrets: Iterable[Secret]) -> bool:
        return any(
            secret.label.startswith(f"{LIBID}-certificate") for secret in secrets if secret.label
        )

    def get_certificate_secret(self, secrets: Iterable[Secret]) -> Secret:
        return next(
            secret
            for secret in secrets
            if secret.label and secret.label.startswith(f"{LIBID}-certificate")
        )

    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharm,
            meta=METADATA,
            config=METADATA["config"],
            actions=METADATA["actions"],
        )

    def test_given_private_key_not_created_and_not_passed_when_certificates_relation_created_then_private_key_is_generated(
        self,
    ):
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
        )

        state_out = self.ctx.run(self.ctx.on.relation_created(certificates_relation), state_in)

        assert self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )
        secret = state_out.get_secret(
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )
        assert secret.latest_content is not None
        private_key = get_private_string_key_from_file()
        assert private_key
        assert private_key != secret.latest_content["private-key"]

    def test_given_private_key_passed_from_charm_when_certificates_relation_created_then_private_key_is_not_stored(
        self,
    ):
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "private_key": get_private_string_key_from_file(),
            },
        )

        state_out = self.ctx.run(self.ctx.on.relation_created(certificates_relation), state_in)

        assert not self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )

    def test_given_private_key_passed_from_charm_not_valid_when_certificates_relation_created_then_error_is_raised(
        self,
    ):
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "private_key": "invalid",
            },
        )

        # Scenario raises this error if the charm raises while handling an event.
        # The charm here would be raising a TLSCertificatesError.
        with pytest.raises(testing.errors.UncaughtCharmError):
            self.ctx.run(self.ctx.on.relation_created(certificates_relation), state_in)

    def test_given_private_key_generated_then_passed_by_charm_then_generated_private_key_secret_is_removed(
        self,
    ):
        private_key = generate_private_key()
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "private_key": get_private_string_key_from_file(),
            },
            secrets=[
                Secret(
                    {"private-key": private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            ],
        )

        state_out = self.ctx.run(self.ctx.on.relation_created(certificates_relation), state_in)

        assert not self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_certificate_requested_when_relation_joined_then_certificate_request_is_added_to_unit_databag(
        self, mock_generate_csr: MagicMock
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        mock_generate_csr.return_value = csr
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "is_ca": False,
            },
            secrets=[
                Secret(
                    {"private-key": private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            ],
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.relations == frozenset({
            testing.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr,
                            "ca": False,
                        }
                    ])
                },
            ),
        })

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    @patch(BASE_CHARM_DIR + "._app_or_unit", MagicMock(return_value=Mode.APP))
    def test_given_certificate_requested_in_app_mode_when_relation_joined_then_certificate_request_is_added_to_app_databag(
        self, mock_generate_csr: MagicMock
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        mock_generate_csr.return_value = csr
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = scenario.State(
            leader=True,
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "is_ca": False,
            },
            secrets=[
                Secret(
                    {"private-key": private_key},
                    label=f"{LIBID}-private-key",
                    owner="unit",
                )
            ],
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)
        assert state_out.relations == frozenset({
            scenario.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_app_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr,
                            "ca": False,
                        }
                    ])
                },
            ),
        })

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_ca_certificate_requested_when_relation_joined_then_certificate_request_is_added_to_databag(
        self, mock_generate_csr: MagicMock
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        mock_generate_csr.return_value = csr
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "is_ca": True,
            },
            secrets={
                Secret(
                    {"private-key": private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            },
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.relations == frozenset({
            testing.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr,
                            "ca": True,
                        }
                    ])
                },
            ),
        })

    def test_given_certificate_in_provider_relation_data_when_relation_changed_then_certificate_available_event_is_emitted(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr = generate_csr(
            private_key=requirer_private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": requirer_private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret},
        )

        self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert len(self.ctx.emitted_events) == 2
        assert isinstance(self.ctx.emitted_events[1], CertificateAvailableEvent)
        assert self.ctx.emitted_events[1].certificate == Certificate.from_string(certificate)
        assert self.ctx.emitted_events[1].ca == Certificate.from_string(provider_ca_certificate)
        assert self.ctx.emitted_events[
            1
        ].certificate_signing_request == CertificateSigningRequest.from_string(csr)

    def test_given_ca_certificate_in_provider_relation_data_when_relation_changed_then_certificate_available_event_is_emitted(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr = generate_csr(
            private_key=requirer_private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
            is_ca=True,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": True,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": requirer_private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )
        state_in = testing.State(
            relations=[certificates_relation],
            config={
                "common_name": "example.com",
                "is_ca": True,
            },
            secrets={private_key_secret},
        )

        self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert len(self.ctx.emitted_events) == 2
        assert isinstance(self.ctx.emitted_events[1], CertificateAvailableEvent)
        assert self.ctx.emitted_events[1].certificate == Certificate.from_string(certificate)
        assert self.ctx.emitted_events[1].ca == Certificate.from_string(provider_ca_certificate)
        assert self.ctx.emitted_events[
            1
        ].certificate_signing_request == CertificateSigningRequest.from_string(csr)

    def test_given_no_request_and_certificate_in_provider_relation_data_when_relation_changed_then_certificate_available_event_is_not_emitted(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr = generate_csr(
            private_key=requirer_private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            ca=provider_ca_certificate,
            csr=csr,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
        )

        self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert len(self.ctx.emitted_events) == 1

    def test_given_certificate_not_requested_when_relation_changed_then_certificate_request_is_removed_from_databag(
        self,
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={},  # Note that there is no `common_name` in the config here
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.relations == frozenset({
            testing.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={},
            ),
        })

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_private_key_does_not_match_with_certificate_requests_when_relation_changed_then_certificate_request_is_replaced_in_databag(
        self, mock_generate_csr: MagicMock
    ):
        initial_private_key = generate_private_key()
        csr = generate_csr(
            private_key=initial_private_key,
            common_name="example.com",
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
        )

        new_private_key = generate_private_key()

        new_csr = generate_csr(
            private_key=new_private_key,
            common_name="example.com",
        )
        mock_generate_csr.return_value = new_csr

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={
                Secret(
                    {"private-key": new_private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                ),
            },
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.relations == frozenset({
            testing.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": new_csr,
                            "ca": False,
                        }
                    ])
                },
            ),
        })

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_certificate_request_changed_when_relation_changed_then_new_certificate_is_requested(
        self, mock_generate_csr: MagicMock
    ):
        private_key = generate_private_key()
        csr_in_relation_data = generate_csr(
            private_key=private_key,
            common_name="old.example.com",
        )
        new_csr = generate_csr(
            private_key=private_key,
            common_name="new.example.com",
        )
        mock_generate_csr.return_value = new_csr
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_in_relation_data,
                        "ca": False,
                    }
                ])
            },
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "new.example.com"},
            secrets={
                Secret(
                    {"private-key": private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            },
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.relations == frozenset({
            testing.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": new_csr,
                            "ca": False,
                        }
                    ])
                },
            ),
        })

    def test_given_revoked_certificate_when_relation_changed_then_certificate_secret_is_removed(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr = generate_csr(
            private_key=requirer_private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                        "revoked": True,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": requirer_private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        certificate_secret = Secret(
            {
                "certificate": certificate,
                "csr": csr,
            },
            label=f"{LIBID}-certificate-0-{get_sha256_hex(csr)}",
            owner="unit",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={
                private_key_secret,
                certificate_secret,
            },
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.secrets == frozenset({
            private_key_secret,
        })

    def test_given_private_key_generated_by_library_is_used_when_regenerate_private_key_then_new_private_key_is_generated(
        self,
    ):
        initial_private_key = "whatever the initial private key is"
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={
                Secret(
                    {"private-key": initial_private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            },
        )

        state_out = self.ctx.run(self.ctx.on.action("regenerate-private-key"), state_in)

        secret = state_out.get_secret(
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )
        assert secret.latest_content is not None
        assert secret.latest_content["private-key"] != initial_private_key

    def test_given_private_key_passed_from_charm_when_regenerate_private_key_then_action_fails(
        self,
    ):
        initial_private_key = "whatever the initial private key is"
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "private_key": get_private_string_key_from_file(),
            },
            secrets={
                Secret(
                    {"private-key": initial_private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            },
        )

        with pytest.raises(ActionFailed):
            self.ctx.run(self.ctx.on.action("regenerate-private-key"), state_in)

    def test_given_private_key_passed_from_charm_when_regenerate_private_key_then_raises_error(
        self,
    ):
        initial_private_key = "whatever the initial private key is"
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "private_key": get_private_string_key_from_file(),
            },
            secrets={
                Secret(
                    {"private-key": initial_private_key},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            },
        )

        with self.ctx(self.ctx.on.update_status(), state_in) as manager:
            with pytest.raises(TLSCertificatesError):
                charm: DummyTLSCertificatesRequirerCharm = manager.charm
                charm.certificates.regenerate_private_key()

    def test_given_certificate_is_provided_when_get_certificate_then_certificate_is_returned(self):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )
        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret},
        )

        self.ctx.run(self.ctx.on.action("get-certificate"), state_in)

        assert self.ctx.action_results == {
            "certificate": certificate,
            "ca": provider_ca_certificate,
            "csr": csr,
        }

    def test_given_provided_certificate_does_not_match_private_key_when_get_certificate_then_certificate_is_not_returned(
        self,
    ):
        private_key = generate_private_key()

        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        bad_private_key = generate_private_key()
        bad_csr = generate_csr(
            private_key=bad_private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        bad_certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=bad_csr,
            ca=provider_ca_certificate,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": bad_certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret},
        )

        with pytest.raises(ActionFailed):
            self.ctx.run(self.ctx.on.action("get-certificate"), state_in)

    @patch(BASE_CHARM_DIR + "._relative_renewal_time")
    def test_given_certificate_is_provided_when_relation_changed_then_certificate_secret_is_created_and_expiry_is_set_correctly(
        self,
        mock_relative_renewal_time: MagicMock,
    ):
        relative_renewal_time = 0.9
        mock_relative_renewal_time.return_value = relative_renewal_time
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        validity_days = 10
        validity = datetime.timedelta(days=validity_days)
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
            validity=validity,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret},
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert self.certificate_secret_exists(state_out.secrets)
        secret = self.get_certificate_secret(state_out.secrets)
        days_to_expiry = validity_days * relative_renewal_time
        assert secret.expire
        assert (
            abs(
                secret.expire
                - (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(days=days_to_expiry)
                )
            ).total_seconds()
            < 60
        )

    def test_given_certificate_secret_exists_and_certificate_is_provided_when_relation_changed_then_certificate_secret_is_updated(
        self,
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )

        initial_certificate_secret = Secret(
            {
                "certificate": "initial certificate",
                "csr": csr,
            },
            label=f"{LIBID}-certificate-0-{get_sha256_hex(csr)}",
            owner="unit",
        )

        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        new_certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": new_certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret, initial_certificate_secret},
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert self.certificate_secret_exists(state_out.secrets)

        certificate_secret = self.get_certificate_secret(state_out.secrets)

        assert certificate_secret.latest_content == {
            "certificate": new_certificate,
            "csr": csr,
        }

    def test_given_certificate_secret_exists_and_certificate_unchanged_when_relation_changed_then_certificate_secret_is_not_updated(
        self,
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )

        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        certificate_secret = Secret(
            {
                "certificate": certificate,
                "csr": csr,
            },
            label=f"{LIBID}-certificate-0-{get_sha256_hex(csr)}",
            owner="unit",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret, certificate_secret},
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert self.certificate_secret_exists(state_out.secrets)

        certificate_secret = self.get_certificate_secret(state_out.secrets)

        assert certificate_secret._latest_revision == 1

    def test_given_multiple_certificates_when_find_available_certificates_then_only_secrets_with_changed_certificates_are_updated(
        self,
    ):
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )

        private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )

        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )

        csr_2 = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )

        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": False,
                    },
                    {
                        "certificate_signing_request": csr_2,
                        "ca": False,
                    },
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate_1,
                        "certificate_signing_request": csr_1,
                        "ca": provider_ca_certificate,
                    },
                    {
                        "certificate": certificate_2,
                        "certificate_signing_request": csr_2,
                        "ca": provider_ca_certificate,
                    },
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )
        certificate_1_secret = Secret(
            {
                "certificate": certificate_1,
                "csr": csr_1,
            },
            label=f"{LIBID}-certificate-0-{get_sha256_hex(csr_1)}",
            owner="unit",
        )
        certificate_2_secret = Secret(
            {
                "certificate": "Content that should be updated",
                "csr": csr_2,
            },
            label=f"{LIBID}-certificate-0-{get_sha256_hex(csr_2)}",
            owner="unit",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={
                private_key_secret,
                certificate_1_secret,
                certificate_2_secret,
            },
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        for secret in state_out.secrets:
            if secret.label == f"{LIBID}-certificate-0-{get_sha256_hex(csr_2)}":
                assert secret.latest_content
                assert secret.latest_content.get("certificate") == certificate_2
            elif secret.label == f"{LIBID}-certificate-0-{get_sha256_hex(csr_1)}":
                assert secret.latest_content
                assert secret.latest_content.get("certificate") == certificate_1

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_certificate_when_certificate_secret_expires_then_new_certificate_is_requested(
        self, mock_generate_csr: MagicMock
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        csr_in_sha256_hex = get_sha256_hex(csr)
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
            validity=datetime.timedelta(hours=1),
        )

        new_csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        assert csr != new_csr
        mock_generate_csr.return_value = new_csr

        certificate_secret = Secret(
            {
                "certificate": certificate,
                "csr": csr,
            },
            label=f"{LIBID}-certificate-0-{csr_in_sha256_hex}",
            owner="unit",
            expire=datetime.datetime.now() - datetime.timedelta(minutes=1),
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={
                private_key_secret,
                certificate_secret,
            },
        )

        state_out = self.ctx.run(
            self.ctx.on.secret_expired(certificate_secret, revision=1), state_in
        )

        assert state_out.relations == frozenset({
            testing.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": new_csr,
                            "ca": False,
                        }
                    ])
                },
                remote_app_data={
                    "certificates": json.dumps([
                        {
                            "certificate": certificate,
                            "certificate_signing_request": csr,
                            "ca": provider_ca_certificate,
                        }
                    ]),
                },
            )
        })

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_certificate_when_renew_certificate_then_new_certificate_is_requested(
        self, mock_generate_csr: MagicMock
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        csr_in_sha256_hex = get_sha256_hex(csr)
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
            validity=datetime.timedelta(hours=1),
        )

        new_csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        assert csr != new_csr
        mock_generate_csr.return_value = new_csr

        certificate_secret = Secret(
            {
                "certificate": certificate,
                "csr": csr,
            },
            label=f"{LIBID}-certificate-0-{csr_in_sha256_hex}",
            owner="unit",
            expire=datetime.datetime.now() - datetime.timedelta(minutes=1),
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={
                private_key_secret,
                certificate_secret,
            },
        )

        state_out = self.ctx.run(self.ctx.on.action("renew-certificates"), state_in)

        assert state_out.relations == frozenset({
            testing.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": new_csr,
                            "ca": False,
                        }
                    ])
                },
                remote_app_data={
                    "certificates": json.dumps([
                        {
                            "certificate": certificate,
                            "certificate_signing_request": csr,
                            "ca": provider_ca_certificate,
                        }
                    ]),
                },
            )
        })

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_new_certificate_request_when_sync_then_new_certificate_is_requested(
        self, mock_generate_csr: MagicMock
    ):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        csr_in_sha256_hex = get_sha256_hex(csr)
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=csr,
            ca=provider_ca_certificate,
            validity=datetime.timedelta(hours=1),
        )

        new_csr = generate_csr(
            private_key=private_key,
            common_name="new-example.com",
        )
        assert csr != new_csr
        mock_generate_csr.return_value = new_csr

        certificate_secret = Secret(
            {
                "certificate": certificate,
                "csr": csr,
            },
            label=f"{LIBID}-certificate-0-{csr_in_sha256_hex}",
            owner="unit",
            expire=datetime.datetime.now() - datetime.timedelta(minutes=1),
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr,
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": csr,
                        "ca": provider_ca_certificate,
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            config={"common_name": "new-example.com"},
            relations={certificates_relation},
            secrets={
                private_key_secret,
                certificate_secret,
            },
        )

        with self.ctx(self.ctx.on.start(), state_in) as manager:
            manager.charm.certificates.sync()
            state_out = manager.run()

            assert state_out.relations == frozenset({
                testing.Relation(
                    id=certificates_relation.id,
                    endpoint="certificates",
                    interface="tls-certificates",
                    remote_app_name="certificate-requirer",
                    local_unit_data={
                        "certificate_signing_requests": json.dumps([
                            {
                                "certificate_signing_request": new_csr,
                                "ca": False,
                            }
                        ])
                    },
                    remote_app_data={
                        "certificates": json.dumps([
                            {
                                "certificate": certificate,
                                "certificate_signing_request": csr,
                                "ca": provider_ca_certificate,
                            }
                        ]),
                    },
                )
            })
