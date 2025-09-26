# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import re
from typing import Any

from ops.charm import ActionEvent, CharmBase
from ops.framework import EventBase
from ops.main import main

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateSigningRequest,
    ProviderCertificate,
    TLSCertificatesProvidesV4,
)


def parse_ca_chain(ca_chain_pem: str) -> list[str]:
    """Return list of certificates based on a PEM CA Chain file.

    Args:
        ca_chain_pem (str): String containing list of certificates. This string should look like:
            -----BEGIN CERTIFICATE-----
            <cert 1>
            -----END CERTIFICATE-----
            -----BEGIN CERTIFICATE-----
            <cert 2>
            -----END CERTIFICATE-----

    Returns:
        list: List of certificates
    """
    chain_list = re.findall(
        pattern="(?=-----BEGIN CERTIFICATE-----)(.*?)(?<=-----END CERTIFICATE-----)",
        string=ca_chain_pem,
        flags=re.DOTALL,
    )
    if not chain_list:
        raise ValueError("No certificate found in chain file")
    return chain_list


class DummyTLSCertificatesProviderCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.certificates = TLSCertificatesProvidesV4(self, "certificates")
        self.framework.observe(self.on.update_status, self._configure)
        self.framework.observe(
            self.on.get_certificate_requests_action, self._on_get_certificate_rquests_action
        )
        self.framework.observe(
            self.on.get_unsolicited_certificates_action,
            self._on_get_unsolicited_certificates_action,
        )
        self.framework.observe(
            self.on.get_outstanding_certificate_requests_action,
            self._on_get_outstanding_certificate_requests_action,
        )
        self.framework.observe(
            self.on.get_issued_certificates_action, self._on_get_issued_certificates_action
        )
        self.framework.observe(
            self.on.set_certificate_action,
            self._on_set_certificate_action,
        )
        self.framework.observe(
            self.on.revoke_all_certificates_action,
            self._on_revoke_all_certificates_action,
        )

    def _configure(self, _: EventBase) -> None:
        certificate_requests = self.certificates.get_outstanding_certificate_requests()
        print("Certificate requests: ", certificate_requests)

    def _on_get_certificate_rquests_action(self, event: ActionEvent) -> None:
        requirer_csrs = self.certificates.get_certificate_requests()
        csrs = [
            {
                "csr": str(requirer_csr.certificate_signing_request),
                "is_ca": requirer_csr.is_ca,
            }
            for requirer_csr in requirer_csrs
        ]
        event.set_results(results={"csrs": csrs})

    def _on_get_unsolicited_certificates_action(self, event: ActionEvent) -> None:
        unsolicited_certificates = self.certificates.get_unsolicited_certificates()
        certificates = [
            {
                "certificate": str(unsolicited_certificate.certificate),
            }
            for unsolicited_certificate in unsolicited_certificates
        ]
        event.set_results(results={"certificates": certificates})

    def _on_get_outstanding_certificate_requests_action(self, event: ActionEvent) -> None:
        outstanding_certificate_requests = self.certificates.get_outstanding_certificate_requests()
        certificate_requests = [
            {
                "csr": str(outstanding_certificate_request.certificate_signing_request),
                "is_ca": outstanding_certificate_request.is_ca,
            }
            for outstanding_certificate_request in outstanding_certificate_requests
        ]
        event.set_results(results={"csrs": certificate_requests})

    def _on_get_issued_certificates_action(self, event: ActionEvent) -> None:
        issued_certificates = self.certificates.get_issued_certificates()
        certificates = [
            {
                "certificate": str(issued_certificate.certificate),
            }
            for issued_certificate in issued_certificates
        ]
        event.set_results(results={"certificates": certificates})

    def _on_set_certificate_action(self, event: ActionEvent) -> None:
        ca_chain_str = event.params.get("ca-chain")
        assert ca_chain_str
        ca_chain_list = parse_ca_chain(base64.b64decode(ca_chain_str).decode())
        csr_str = base64.b64decode(event.params["certificate-signing-request"]).decode("utf-8")
        certificate_str = base64.b64decode(event.params["certificate"]).decode("utf-8")
        ca_str = base64.b64decode(event.params["ca-certificate"]).decode("utf-8")
        self.certificates.set_relation_certificate(
            provider_certificate=ProviderCertificate(
                relation_id=event.params["relation-id"],
                certificate=Certificate.from_string(certificate_str),
                certificate_signing_request=CertificateSigningRequest.from_string(csr_str),
                ca=Certificate.from_string(ca_str),
                chain=[
                    Certificate.from_string(ca_certificate) for ca_certificate in ca_chain_list
                ],
            ),
        )

    def _on_revoke_all_certificates_action(self, event: ActionEvent) -> None:
        self.certificates.revoke_all_certificates()


if __name__ == "__main__":
    main(DummyTLSCertificatesProviderCharm)
