# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import datetime
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
import scenario
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from ops import testing
from ops.charm import ActionEvent, CharmBase
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
    CertificateRequestAttributes,
    CertificateSigningRequest,
    Mode,
    PrivateKey,
    ProviderCapabilities,
    TLSCertificatesError,
    TLSCertificatesRequiresV4,
)
from requirer_charm import (
    DummyTLSCertificatesRequirerCharm,
    DummyTLSCertificatesRequirerCharmAppAndUnit,
    DummyTLSCertificatesRequirerCharmAppAndUnitDuplicate,
    DummyTLSCertificatesRequirerCharmAppAndUnitWithPrivateKey,
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

    def certificate_secret_exists(
        self, secrets: Iterable[Secret], label: str | None = None
    ) -> bool:
        if label:
            return any(secret.label == label for secret in secrets)
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

    def test_given_app_and_unit_mode_when_relation_created_and_leader_then_private_keys_are_generated(
        self,
    ):
        ctx = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharmAppAndUnit,
            meta=METADATA,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_created(certificates_relation), state_in)

        assert self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )
        assert self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-{certificates_relation.endpoint}"
        )

    def test_given_app_and_unit_mode_when_relation_created_and_not_leader_then_only_unit_private_key_is_generated(
        self,
    ):
        ctx = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharmAppAndUnit,
            meta=METADATA,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            leader=False,
        )

        state_out = ctx.run(ctx.on.relation_created(certificates_relation), state_in)

        assert self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )
        assert not self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-{certificates_relation.endpoint}"
        )

    def test_given_app_and_unit_mode_with_private_key_when_relation_created_then_no_private_key_secrets_are_created(
        self,
    ):
        ctx = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharmAppAndUnitWithPrivateKey,
            meta=METADATA,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            leader=True,
            config={
                "private_key": get_private_string_key_from_file(),
            },
        )

        state_out = ctx.run(ctx.on.relation_created(certificates_relation), state_in)

        assert not self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )
        assert not self.private_key_secret_exists(
            state_out.secrets, f"{LIBID}-private-key-{certificates_relation.endpoint}"
        )

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_app_and_unit_mode_when_relation_changed_and_leader_then_requests_added_to_app_and_unit_databags(
        self, mock_generate_csr: MagicMock
    ):
        ctx = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharmAppAndUnit,
            meta=METADATA,
        )
        csr_app = generate_csr(private_key=generate_private_key(), common_name="app.example.com")
        csr_unit = generate_csr(private_key=generate_private_key(), common_name="unit.example.com")
        mock_generate_csr.side_effect = [csr_app, csr_unit]
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = scenario.State(
            leader=True,
            relations={certificates_relation},
        )

        state_out = ctx.run(ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.relations == frozenset({
            scenario.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_app_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": str(csr_app),
                            "ca": False,
                        }
                    ])
                },
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": str(csr_unit),
                            "ca": False,
                        }
                    ])
                },
            ),
        })

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_app_and_unit_mode_when_relation_changed_and_not_leader_then_only_unit_request_is_added(
        self, mock_generate_csr: MagicMock
    ):
        ctx = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharmAppAndUnit,
            meta=METADATA,
        )
        csr_unit = generate_csr(private_key=generate_private_key(), common_name="unit.example.com")
        mock_generate_csr.return_value = csr_unit
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = scenario.State(
            leader=False,
            relations={certificates_relation},
        )

        state_out = ctx.run(ctx.on.relation_changed(certificates_relation), state_in)

        assert mock_generate_csr.call_count == 1
        assert state_out.relations == frozenset({
            scenario.Relation(
                id=certificates_relation.id,
                endpoint="certificates",
                interface="tls-certificates",
                remote_app_name="certificate-requirer",
                local_unit_data={
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": str(csr_unit),
                            "ca": False,
                        }
                    ])
                },
            ),
        })

    def test_given_app_and_unit_mode_with_duplicate_requests_then_error_is_raised(self):
        ctx = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharmAppAndUnitDuplicate,
            meta=METADATA,
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = testing.State(
            relations={certificates_relation},
            leader=True,
        )

        with pytest.raises(
            testing.errors.UncaughtCharmError,
            match="Duplicate certificate request found in both APP and UNIT modes",
        ):
            ctx.run(ctx.on.relation_created(certificates_relation), state_in)

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

    def test_given_library_generated_key_when_import_valid_private_key_then_key_is_imported(
        self,
    ):
        initial_private_key = "initial library generated key"
        external_private_key = generate_private_key()

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
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

        state_out = self.ctx.run(
            self.ctx.on.action(
                "import-private-key", params={"private-key": str(external_private_key)}
            ),
            state_in,
        )

        secret = state_out.get_secret(
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}"
        )
        assert secret.latest_content is not None
        assert secret.latest_content["private-key"] == str(external_private_key)
        assert secret.latest_content["private-key"] != initial_private_key

    def test_given_weak_private_key_when_import_private_key_then_raises_error(self):
        """Test that importing a weak private key raises TLSCertificatesError."""
        weak_key = PrivateKey.from_string(generate_private_key(key_size=1024))

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={
                Secret(
                    {"private-key": "initial-key"},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            },
        )

        with self.ctx(self.ctx.on.update_status(), state_in) as manager:
            charm: DummyTLSCertificatesRequirerCharm = manager.charm

            with pytest.raises(TLSCertificatesError, match="Invalid private key"):
                charm.certificates.import_private_key(weak_key)

    def test_given_private_key_from_charm_when_import_private_key_then_raises_error(self):
        """Test that import raises error when private key was passed via charm config."""
        external_private_key = PrivateKey.from_string(generate_private_key())

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )

        state_in = testing.State(
            relations={certificates_relation},
            config={
                "common_name": "example.com",
                "private_key": get_private_string_key_from_file(),
            },
        )

        with self.ctx(self.ctx.on.update_status(), state_in) as manager:
            charm: DummyTLSCertificatesRequirerCharm = manager.charm

            with pytest.raises(TLSCertificatesError, match="Private key is passed by the charm"):
                charm.certificates.import_private_key(external_private_key)

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

    def test_given_request_error_in_relation_data_when_get_request_errors_then_errors_are_returned(
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
            remote_app_name="certificate-provider",
            remote_app_data={
                "request_errors": json.dumps([
                    {
                        "csr": csr,
                        "error": {
                            "code": 101,
                            "name": "IP_NOT_ALLOWED",
                            "message": "IP address not allowed",
                            "reason": "IP addresses are not permitted",
                            "provider": "test-provider",
                            "endpoint": "certificates",
                        },
                    }
                ]),
            },
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets=[
                Secret(
                    {"private-key": str(private_key)},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            ],
        )

        self.ctx.run(self.ctx.on.action("get-request-errors"), state_in)

        assert self.ctx.action_results
        errors = self.ctx.action_results["errors"]
        assert len(errors) == 1
        assert errors[0]["code"] == 101
        assert errors[0]["message"] == "IP address not allowed"

    def test_given_request_error_when_get_request_error_for_csr_then_specific_error_is_returned(
        self,
    ):
        private_key = generate_private_key()
        csr1 = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        csr2 = generate_csr(
            private_key=private_key,
            common_name="example.org",
        )
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            remote_app_data={
                "request_errors": json.dumps([
                    {
                        "csr": csr1,
                        "error": {
                            "code": 101,
                            "name": "IP_NOT_ALLOWED",
                            "message": "IP address not allowed",
                            "reason": "IP addresses are not permitted",
                            "provider": "test-provider",
                            "endpoint": "certificates",
                        },
                    },
                    {
                        "csr": csr2,
                        "error": {
                            "code": 102,
                            "name": "DOMAIN_NOT_ALLOWED",
                            "message": "Domain not allowed",
                            "reason": "Domain is restricted",
                            "provider": "test-provider",
                            "endpoint": "certificates",
                        },
                    },
                ]),
            },
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets=[
                Secret(
                    {"private-key": str(private_key)},
                    label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
                    owner="unit",
                )
            ],
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        self.ctx.run(self.ctx.on.action("get-request-errors"), state_out)
        assert self.ctx.action_results is not None
        errors = self.ctx.action_results["errors"]
        assert len(errors) == 2
        assert errors[0]["code"] == 101
        assert errors[0]["message"] == "IP address not allowed"
        assert errors[1]["code"] == 102
        assert errors[1]["message"] == "Domain not allowed"

    def test_given_library_generated_private_key_when_get_private_key_secret_id_then_secret_id_is_returned(
        self,
    ):
        private_key = generate_private_key()
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )
        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret},
        )

        state_out = self.ctx.run(self.ctx.on.action("get-private-key-secret-id"), state_in)

        assert self.ctx.action_results is not None
        result_secret_id = self.ctx.action_results["secret-id"]
        assert result_secret_id != ""
        assert result_secret_id.startswith("secret:")

        secret_in_state = next(
            (s for s in state_out.secrets if s.label == private_key_secret.label), None
        )
        assert secret_in_state is not None
        assert result_secret_id == secret_in_state.id

    def test_given_no_private_key_generated_when_get_private_key_secret_id_then_none_is_returned(
        self,
    ):
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
        )

        self.ctx.run(self.ctx.on.action("get-private-key-secret-id"), state_in)
        assert self.ctx.action_results == {"secret-id": ""}

    @patch(BASE_CHARM_DIR + "._app_or_unit")
    def test_given_app_mode_non_leader_when_get_private_key_secret_id_then_none_is_returned(
        self, mock_app_or_unit: MagicMock
    ):
        mock_app_or_unit.return_value = Mode.APP
        private_key = generate_private_key()
        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )
        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-{certificates_relation.endpoint}",
            owner="app",
        )
        state_in = testing.State(
            relations={certificates_relation},
            config={"common_name": "example.com"},
            secrets={private_key_secret},
            leader=False,
        )

        self.ctx.run(self.ctx.on.action("get-private-key-secret-id"), state_in)
        assert self.ctx.action_results == {"secret-id": ""}

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_certificate_past_safety_threshold_when_configure_then_certificate_is_renewed(
        self, mock_generate_csr: MagicMock
    ):
        validity_days = 365
        days_elapsed = 362

        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
            validity=datetime.timedelta(days=validity_days),
        )

        csr_object = x509.load_pem_x509_csr(csr.encode())
        issuer = x509.load_pem_x509_certificate(provider_ca_certificate.encode()).issuer
        ca_private_key_object = serialization.load_pem_private_key(
            provider_private_key.encode(), password=None
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        not_valid_before = now - datetime.timedelta(days=days_elapsed)
        not_valid_after = not_valid_before + datetime.timedelta(days=validity_days)

        cert = (
            x509.CertificateBuilder()
            .subject_name(csr_object.subject)
            .issuer_name(issuer)
            .public_key(csr_object.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_valid_before)
            .not_valid_after(not_valid_after)
            .sign(ca_private_key_object, hashes.SHA256())  # type: ignore[arg-type]
        )
        certificate = cert.public_bytes(serialization.Encoding.PEM).decode().strip()

        new_csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        mock_generate_csr.return_value = new_csr

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": str(csr),
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": str(certificate),
                        "certificate_signing_request": str(csr),
                        "ca": str(provider_ca_certificate),
                        "chain": [str(certificate), str(provider_ca_certificate)],
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={private_key_secret},
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        updated_relation = state_out.get_relation(certificates_relation.id)
        csrs_data = json.loads(updated_relation.local_unit_data["certificate_signing_requests"])
        assert len(csrs_data) == 1
        assert csrs_data[0]["certificate_signing_request"] == str(new_csr)
        assert csrs_data[0]["certificate_signing_request"] != str(csr)

    @patch(LIB_DIR + ".CertificateRequestAttributes.generate_csr")
    def test_given_certificate_before_safety_threshold_when_configure_then_certificate_is_not_renewed(
        self, mock_generate_csr: MagicMock
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
            validity=datetime.timedelta(days=365),
        )
        certificate = generate_certificate(
            ca=provider_ca_certificate,
            ca_key=provider_private_key,
            csr=csr,
            validity=datetime.timedelta(days=365),
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": str(csr),
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": str(certificate),
                        "certificate_signing_request": str(csr),
                        "ca": str(provider_ca_certificate),
                        "chain": [str(certificate), str(provider_ca_certificate)],
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={private_key_secret},
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        updated_relation = state_out.get_relation(certificates_relation.id)
        csrs_data = json.loads(updated_relation.local_unit_data["certificate_signing_requests"])
        assert len(csrs_data) == 1
        assert csrs_data[0]["certificate_signing_request"] == str(csr)
        mock_generate_csr.assert_not_called()

    def test_given_non_leader_unit_when_relation_broken_then_unit_secrets_are_cleaned_up(self):
        private_key = generate_private_key()

        context = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharm,
            meta=METADATA,
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )

        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={private_key_secret},
        )

        state_out = context.run(context.on.relation_broken(certificates_relation), state_in)

        assert not self.private_key_secret_exists(
            state_out.secrets,
            f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
        )

    def test_given_leader_unit_when_relation_broken_then_unit_and_app_secrets_are_cleaned_up(self):
        private_key = generate_private_key()

        context = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharm,
            meta=METADATA,
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )

        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-{certificates_relation.endpoint}",
            owner="app",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={private_key_secret},
            leader=True,
        )

        with patch.object(
            DummyTLSCertificatesRequirerCharm, "_app_or_unit", return_value=Mode.APP
        ):
            state_out = context.run(context.on.relation_broken(certificates_relation), state_in)

        assert not self.private_key_secret_exists(
            state_out.secrets,
            f"{LIBID}-private-key-{certificates_relation.endpoint}",
        )

    def test_given_non_leader_unit_when_relation_broken_then_app_secrets_are_not_cleaned_up(self):
        private_key = generate_private_key()

        context = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharm,
            meta=METADATA,
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )

        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-{certificates_relation.endpoint}",
            owner="app",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={private_key_secret},
            leader=False,
        )

        with patch.object(
            DummyTLSCertificatesRequirerCharm, "_app_or_unit", return_value=Mode.APP
        ):
            state_out = context.run(context.on.relation_broken(certificates_relation), state_in)

        assert self.private_key_secret_exists(
            state_out.secrets,
            f"{LIBID}-private-key-{certificates_relation.endpoint}",
        )

    def test_given_certificate_secrets_when_relation_broken_then_secrets_are_cleaned_up(self):
        private_key = generate_private_key()
        csr = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )

        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="ca.example.com",
        )
        certificate = generate_certificate(
            ca=provider_ca_certificate,
            ca_key=provider_private_key,
            csr=csr,
            validity=datetime.timedelta(days=365),
        )

        context = testing.Context(
            charm_type=DummyTLSCertificatesRequirerCharm,
            meta=METADATA,
        )

        certificates_relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": str(csr),
                        "ca": False,
                    }
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": str(certificate),
                        "certificate_signing_request": str(csr),
                        "ca": str(provider_ca_certificate),
                        "chain": [str(certificate), str(provider_ca_certificate)],
                    }
                ]),
            },
        )

        private_key_secret = Secret(
            {"private-key": str(private_key)},
            label=f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
            owner="unit",
        )

        csr_obj = CertificateSigningRequest.from_string(str(csr))
        csr_hash = csr_obj.get_sha256_hex()
        certificate_secret_label = (
            f"{LIBID}-certificate-0-{certificates_relation.endpoint}-{csr_hash}"
        )

        certificate_secret = Secret(
            {"certificate": str(certificate), "csr": str(csr)},
            label=certificate_secret_label,
            owner="unit",
        )

        state_in = testing.State(
            config={"common_name": "example.com"},
            relations={certificates_relation},
            secrets={private_key_secret, certificate_secret},
        )

        with patch(
            "charmlibs.interfaces.tls_certificates._tls_certificates."
            "TLSCertificatesRequiresV4._list_secrets"
        ) as mock_list_secrets:
            mock_list_secrets.return_value = [certificate_secret.id]
            state_out = context.run(context.on.relation_broken(certificates_relation), state_in)

        assert not self.private_key_secret_exists(
            state_out.secrets,
            f"{LIBID}-private-key-0-{certificates_relation.endpoint}",
        )

        assert not any(secret.label == certificate_secret_label for secret in state_out.secrets)


CAPABILITY_REQUIRER_META = {
    "name": "tls-certificates-capability-requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}

CAPABILITY_REQUIRER_ACTIONS = {
    "get-provider-capabilities": {"description": "Return the provider's advertised capabilities."},
}


class CapabilityRequirerCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=[CertificateRequestAttributes(common_name="example.com")],
        )
        self.framework.observe(
            self.on.get_provider_capabilities_action,
            self._on_get_provider_capabilities_action,
        )

    def _on_get_provider_capabilities_action(self, event: ActionEvent) -> None:
        capabilities = self.certificates.get_provider_capabilities()
        if capabilities is None:
            event.set_results({"available": False})
            return
        event.set_results({
            "available": True,
            "provider-type": capabilities.provider_type or "",
            "supports-ip-sans": str(capabilities.supports_ip_sans),
        })


class TestRequirerGetProviderCapabilities:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = testing.Context(
            charm_type=CapabilityRequirerCharm,
            meta=CAPABILITY_REQUIRER_META,
            actions=CAPABILITY_REQUIRER_ACTIONS,
        )

    def _run_action(self, state_in: testing.State) -> dict[str, Any]:
        self.ctx.run(self.ctx.on.action("get-provider-capabilities"), state_in)
        return self.ctx.action_results or {}

    def test_given_provider_advertises_capabilities_when_get_then_returned(self):
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            remote_app_data={
                "capabilities": json.dumps({
                    "supports_ip_sans": False,
                    "provider_type": "vault",
                })
            },
        )
        state_in = testing.State(relations={relation}, leader=True)

        results = self._run_action(state_in)

        assert results["available"] is True
        assert results["provider-type"] == "vault"
        assert results["supports-ip-sans"] == "False"

    def test_given_no_relation_when_get_then_unavailable(self):
        state_in = testing.State(leader=True)

        results = self._run_action(state_in)

        assert results["available"] is False

    def test_given_legacy_provider_without_capabilities_when_get_then_unavailable(self):
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            remote_app_data={"certificates": json.dumps([])},
        )
        state_in = testing.State(relations={relation}, leader=True)

        results = self._run_action(state_in)

        assert results["available"] is False

    def test_given_invalid_provider_data_when_get_then_unavailable(self):
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            remote_app_data={"capabilities": "not-json"},
        )
        state_in = testing.State(relations={relation}, leader=True)

        results = self._run_action(state_in)

        assert results["available"] is False


class CallableRequirerCharm(CharmBase):
    calls = 0
    received_capabilities: ClassVar[list[ProviderCapabilities | None]] = []

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=self._build_requests,
        )

    def _build_requests(
        self, capabilities: ProviderCapabilities | None
    ) -> list[CertificateRequestAttributes]:
        CallableRequirerCharm.calls += 1
        CallableRequirerCharm.received_capabilities.append(capabilities)
        if capabilities is None:
            # Provider has not advertised capabilities yet: use a safe default.
            common_name = "default.example.com"
        elif capabilities.supports_ip_sans is False:
            common_name = "adapted.example.com"
        else:
            common_name = "advertised.example.com"
        return [CertificateRequestAttributes(common_name=common_name)]


class TestRequirerCallableCertificateRequests:
    @pytest.fixture(autouse=True)
    def context(self):
        CallableRequirerCharm.calls = 0
        CallableRequirerCharm.received_capabilities = []
        self.ctx = testing.Context(
            charm_type=CallableRequirerCharm,
            meta=CAPABILITY_REQUIRER_META,
        )

    def _csr_common_names(self, state_out: testing.State, relation_id: int) -> list[str]:
        relation = next(r for r in state_out.relations if r.id == relation_id)
        raw = relation.local_unit_data.get("certificate_signing_requests")
        if not raw:
            return []
        names: list[str] = []
        for entry in json.loads(raw):
            csr = x509.load_pem_x509_csr(entry["certificate_signing_request"].encode())
            names.extend(
                str(attr.value)
                for attr in csr.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
            )
        return names

    def test_given_callable_requests_when_relation_changed_then_csr_uses_callable_result(self):
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )
        state_in = testing.State(relations={relation})

        state_out = self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        assert self._csr_common_names(state_out, relation.id) == ["default.example.com"]

    def test_given_callable_reads_capabilities_when_relation_changed_then_request_is_adapted(self):
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            remote_app_data={"capabilities": json.dumps({"supports_ip_sans": False})},
        )
        state_in = testing.State(relations={relation})

        state_out = self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        assert self._csr_common_names(state_out, relation.id) == ["adapted.example.com"]

    def test_given_callable_requests_when_relation_changed_then_callable_resolved_once(self):
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )
        state_in = testing.State(relations={relation})

        self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        assert CallableRequirerCharm.calls == 1

    def test_given_no_capabilities_advertised_when_relation_changed_then_callable_receives_none(
        self,
    ):
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
        )
        state_in = testing.State(relations={relation})

        self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        assert CallableRequirerCharm.received_capabilities == [None]

    def test_given_empty_capabilities_advertised_when_relation_changed_then_callable_receives_object(
        self,
    ):
        # An advertised-but-empty capabilities object must be distinguishable from "not
        # advertised yet" (None), so capability-driven request shaping can be deterministic.
        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            remote_app_data={"capabilities": json.dumps({})},
        )
        state_in = testing.State(relations={relation})

        self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        received = CallableRequirerCharm.received_capabilities
        assert len(received) == 1
        assert isinstance(received[0], ProviderCapabilities)
        assert received[0].supports_ip_sans is None

    def test_given_callable_when_certificate_secret_expires_then_renewed_csr_is_sent(self):
        # Renewal runs on secret_expired, which does not go through _configure. The callable
        # must still be resolved so the renewed CSR is re-sent (a static list works here, so a
        # callable must not be strictly more fragile).
        private_key = generate_private_key()
        old_csr = generate_csr(private_key=private_key, common_name="default.example.com")
        csr_sha256 = get_sha256_hex(old_csr)
        provider_private_key = generate_private_key()
        provider_ca = generate_ca(private_key=provider_private_key, common_name="ca.example.com")
        certificate = generate_certificate(
            ca_key=provider_private_key,
            csr=old_csr,
            ca=provider_ca,
            validity=datetime.timedelta(hours=1),
        )

        relation = testing.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-provider",
            local_unit_data={
                "certificate_signing_requests": json.dumps([
                    {"certificate_signing_request": old_csr, "ca": False}
                ])
            },
            remote_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate,
                        "certificate_signing_request": old_csr,
                        "ca": provider_ca,
                    }
                ]),
            },
        )
        private_key_secret = Secret(
            {"private-key": private_key},
            label=f"{LIBID}-private-key-0-{relation.endpoint}",
            owner="unit",
        )
        certificate_secret = Secret(
            {"certificate": certificate, "csr": old_csr},
            label=f"{LIBID}-certificate-0-{csr_sha256}",
            owner="unit",
            expire=datetime.datetime.now() - datetime.timedelta(minutes=1),
        )
        state_in = testing.State(
            relations={relation},
            secrets={private_key_secret, certificate_secret},
        )

        state_out = self.ctx.run(
            self.ctx.on.secret_expired(certificate_secret, revision=1), state_in
        )

        assert self._csr_common_names(state_out, relation.id) == ["default.example.com"]
