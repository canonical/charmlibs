# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import json
from pathlib import Path

import pytest
import scenario
import yaml

from certificates import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)
from provider_charm import DummyTLSCertificatesProviderCharm

METADATA = yaml.safe_load(
    (Path(__file__).parent / "dummy_provider_charm" / "charmcraft.yaml").read_text()
)


class TestTLSCertificatesProvidesV4:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = scenario.Context(
            charm_type=DummyTLSCertificatesProviderCharm,
            meta=METADATA,
            actions=METADATA["actions"],
        )

    def test_given_no_certificate_requests_when_get_requirer_csrs_then_no_csrs_are_returned(
        self,
    ):
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-certificate-requests"), state_in)

        assert self.ctx.action_results == {"csrs": []}

    def test_given_unit_certificate_requests_when_get_requirer_csrs_then_csrs_are_returned(self):
        private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        csr_2 = generate_csr(
            private_key=private_key,
            common_name="example.org",
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            remote_units_data={
                0: {
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr_1,
                            "ca": "false",
                        },
                        {
                            "certificate_signing_request": csr_2,
                            "ca": "false",
                        },
                    ])
                }
            },
        )

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-certificate-requests"), state_in)

        assert self.ctx.action_results == {
            "csrs": [{"csr": csr_1, "is_ca": False}, {"csr": csr_2, "is_ca": False}]
        }

    def test_given_app_certificate_requests_when_get_requirer_csrs_then_csrs_are_returned(self):
        private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=private_key,
            common_name="example.com",
        )
        csr_2 = generate_csr(
            private_key=private_key,
            common_name="example.org",
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    },
                    {
                        "certificate_signing_request": csr_2,
                        "ca": "false",
                    },
                ])
            },
        )

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-certificate-requests"), state_in)

        assert self.ctx.action_results == {
            "csrs": [{"csr": csr_1, "is_ca": False}, {"csr": csr_2, "is_ca": False}]
        }

    def test_given_no_certificate_when_get_issued_certificates_then_no_certificate_is_returned(
        self,
    ):
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-issued-certificates"), state_in)

        assert self.ctx.action_results == {"certificates": []}

    def test_given_all_certificates_are_solicited_when_get_unsolicited_certificates_then_no_certificate_is_returned(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
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
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    }
                ]),
            },
            remote_units_data={
                0: {
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr_2,
                            "ca": "false",
                        },
                    ])
                }
            },
        )
        state_in = scenario.State(
            relations=[certificates_relation],
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-unsolicited-certificates"), state_in)

        assert self.ctx.action_results == {"certificates": []}

    def test_given_unsolicited_certificates_when_get_unsolicited_certificates_then_certificates_are_returned(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
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
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    }
                ]),
            },
        )
        state_in = scenario.State(
            relations=[certificates_relation],
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-unsolicited-certificates"), state_in)

        assert self.ctx.action_results == {"certificates": [{"certificate": certificate_2}]}

    def test_given_no_request_when_get_outstanding_certificate_requests_then_no_csr_is_returned(
        self,
    ):
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
        )
        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-outstanding-certificate-requests"), state_in)

        assert self.ctx.action_results == {"csrs": []}

    def test_given_certificate_requests_fulfilled_when_get_outstanding_certificate_requests_then_no_csr_is_returned(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
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
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    }
                ]),
            },
            remote_units_data={
                0: {
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr_2,
                            "ca": "false",
                        },
                    ])
                }
            },
        )

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-outstanding-certificate-requests"), state_in)

        assert self.ctx.action_results == {"csrs": []}

    def test_given_unfulfilled_certificate_request_when_get_outstanding_certificate_requests_then_csr_is_returned(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate_1,
                        "certificate_signing_request": csr_1,
                        "ca": provider_ca_certificate,
                    },
                ]),
            },
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    }
                ]),
            },
            remote_units_data={
                0: {
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr_2,
                            "ca": "false",
                        },
                    ])
                }
            },
        )

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-outstanding-certificate-requests"), state_in)

        assert self.ctx.action_results == {"csrs": [{"csr": csr_2, "is_ca": False}]}

    def test_given_certificates_when_get_issued_certificates_then_certificates_are_returned(self):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
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

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        self.ctx.run(self.ctx.on.action("get-issued-certificates"), state_in)

        assert self.ctx.action_results == {
            "certificates": [{"certificate": certificate_1}, {"certificate": certificate_2}]
        }

    def test_given_certificate_request_when_set_relation_certificate_then_certificate_added_to_relation_data(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate_1,
                        "certificate_signing_request": csr_1,
                        "ca": provider_ca_certificate,
                        "chain": [provider_ca_certificate],
                    }
                ]),
            },
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    }
                ]),
            },
            remote_units_data={
                0: {
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr_2,
                            "ca": "false",
                        },
                    ])
                }
            },
        )

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )
        params = {
            "certificate": base64.b64encode(certificate_2.encode()).decode(),
            "certificate-signing-request": base64.b64encode(csr_2.encode()).decode(),
            "ca-certificate": base64.b64encode(provider_ca_certificate.encode()).decode(),
            "ca-chain": base64.b64encode(provider_ca_certificate.encode()).decode(),
            "relation-id": certificates_relation.id,
        }
        state_out = self.ctx.run(self.ctx.on.action("set-certificate", params=params), state_in)

        certificates = json.loads(
            state_out.get_relation(certificates_relation.id).local_app_data["certificates"]
        )
        assert certificates == [
            {
                "certificate": certificate_1,
                "certificate_signing_request": csr_1,
                "ca": provider_ca_certificate,
                "chain": [provider_ca_certificate],
            },
            {
                "certificate": certificate_2,
                "certificate_signing_request": csr_2,
                "ca": provider_ca_certificate,
                "chain": [provider_ca_certificate],
            },
        ]

    def test_given_certificate_exists_for_request_when_set_relation_certificate_then_request_is_overwritten(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate_1,
                        "certificate_signing_request": csr_1,
                        "ca": provider_ca_certificate,
                        "chain": [provider_ca_certificate],
                    },
                    {
                        "certificate": certificate_2,
                        "certificate_signing_request": csr_2,
                        "ca": provider_ca_certificate,
                        "chain": [provider_ca_certificate],
                    },
                ]),
            },
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    }
                ]),
            },
            remote_units_data={
                0: {
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr_2,
                            "ca": "false",
                        },
                    ])
                }
            },
        )

        new_certificate_for_csr_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        params = {
            "certificate": base64.b64encode(new_certificate_for_csr_1.encode()).decode(),
            "certificate-signing-request": base64.b64encode(csr_1.encode()).decode(),
            "ca-certificate": base64.b64encode(provider_ca_certificate.encode()).decode(),
            "ca-chain": base64.b64encode(provider_ca_certificate.encode()).decode(),
            "relation-id": certificates_relation.id,
        }

        state_out = self.ctx.run(self.ctx.on.action("set-certificate", params=params), state_in)

        certificates = json.loads(
            state_out.get_relation(certificates_relation.id).local_app_data["certificates"]
        )
        assert certificates == [
            {
                "certificate": certificate_2,
                "certificate_signing_request": csr_2,
                "ca": provider_ca_certificate,
                "chain": [provider_ca_certificate],
            },
            {
                "certificate": new_certificate_for_csr_1,
                "certificate_signing_request": csr_1,
                "ca": provider_ca_certificate,
                "chain": [provider_ca_certificate],
            },
        ]

    def test_given_certificates_when_revoke_all_certificates_then_certificates_are_revoked(self):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="1.example.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="2.example.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
                "certificates": json.dumps([
                    {
                        "certificate": certificate_1,
                        "certificate_signing_request": csr_1,
                        "ca": provider_ca_certificate,
                        "chain": [provider_ca_certificate],
                    },
                    {
                        "certificate": certificate_2,
                        "certificate_signing_request": csr_2,
                        "ca": provider_ca_certificate,
                        "chain": [provider_ca_certificate],
                    },
                ]),
            },
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    }
                ]),
            },
            remote_units_data={
                0: {
                    "certificate_signing_requests": json.dumps([
                        {
                            "certificate_signing_request": csr_2,
                            "ca": "false",
                        },
                    ])
                }
            },
        )

        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        state_out = self.ctx.run(self.ctx.on.action("revoke-all-certificates"), state_in)

        certificates = json.loads(
            state_out.get_relation(certificates_relation.id).local_app_data["certificates"]
        )

        assert certificates == [
            {
                "certificate": certificate_1,
                "certificate_signing_request": csr_1,
                "ca": provider_ca_certificate,
                "chain": [provider_ca_certificate],
                "revoked": True,
            },
            {
                "certificate": certificate_2,
                "certificate_signing_request": csr_2,
                "ca": provider_ca_certificate,
                "chain": [provider_ca_certificate],
                "revoked": True,
            },
        ]

    def test_given_certificates_for_which_no_csr_exists_when_relation_changed_then_certificates_removed(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data={
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
        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.get_relation(certificates_relation.id).local_app_data == {}

    def test_given_fulfilled_certificate_requests_when_relation_changed_then_certificates_removed(
        self,
    ):
        requirer_private_key = generate_private_key()
        csr_1 = generate_csr(
            private_key=requirer_private_key,
            common_name="example1.com",
        )
        csr_2 = generate_csr(
            private_key=requirer_private_key,
            common_name="example2.org",
        )
        provider_private_key = generate_private_key()
        provider_ca_certificate = generate_ca(
            private_key=provider_private_key,
            common_name="example.com",
        )
        certificate_1 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_1,
            ca=provider_ca_certificate,
        )
        certificate_2 = generate_certificate(
            ca_key=provider_private_key,
            csr=csr_2,
            ca=provider_ca_certificate,
        )
        local_app_data = {
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
        }
        certificates_relation = scenario.Relation(
            endpoint="certificates",
            interface="tls-certificates",
            remote_app_name="certificate-requirer",
            local_app_data=local_app_data,
            remote_app_data={
                "certificate_signing_requests": json.dumps([
                    {
                        "certificate_signing_request": csr_1,
                        "ca": "false",
                    },
                    {
                        "certificate_signing_request": csr_2,
                        "ca": "true",
                    },
                ])
            },
        )
        state_in = scenario.State(
            relations={certificates_relation},
            leader=True,
        )

        state_out = self.ctx.run(self.ctx.on.relation_changed(certificates_relation), state_in)

        assert state_out.get_relation(certificates_relation.id).local_app_data == local_app_data
