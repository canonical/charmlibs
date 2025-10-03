#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import Any

from ops import EventBase, main
from ops.charm import CharmBase, CollectStatusEvent
from ops.model import ActiveStatus, BlockedStatus, SecretNotFoundError, WaitingStatus
from self_signed_certificates import (
    generate_ca,
    generate_certificate,
    generate_private_key,
)

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    ProviderCertificate,
    TLSCertificatesProvidesV4,
)

CERTIFICATE_VALIDITY = 0.003  # Around 4 minutes
CA_COMMON_NAME = "pizza"

logger = logging.getLogger(__name__)


class DummyTLSCertificatesProviderCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.certificates = TLSCertificatesProvidesV4(self, "certificates")
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        self.framework.observe(self.on.install, self._configure)
        self.framework.observe(self.on.update_status, self._configure)
        self.framework.observe(
            self.on.certificates_relation_changed,
            self._configure,
        )

    def _on_collect_unit_status(self, event: CollectStatusEvent) -> None:
        if not self._relation_created("certificates"):
            event.add_status(BlockedStatus("Missing relation to certificates requirer"))
            return
        root_certificate, root_key = self._get_root_certificate()
        if not root_certificate or not root_key:
            event.add_status(WaitingStatus("Waiting for CA certificate"))
            return
        event.add_status(ActiveStatus())

    def _configure(self, event: EventBase) -> None:
        if not self.unit.is_leader():
            logger.info("Not a leader")
            return
        root_certificate, root_key = self._get_root_certificate()
        if not root_certificate or not root_key:
            self._generate_root_certificates()
        self._sync_certificates()

    def _sync_certificates(self) -> None:
        root_certificate, root_key = self._get_root_certificate()
        if not root_certificate or not root_key:
            logger.info("Root certificates are not yet set")
            return
        for relation in self.model.relations["certificates"]:
            certificate_requests = self.certificates.get_outstanding_certificate_requests(
                relation_id=relation.id
            )
            for certificate_request in certificate_requests:
                certificate = generate_certificate(
                    ca=root_certificate.encode(),
                    ca_key=root_key.encode(),
                    csr=str(certificate_request.certificate_signing_request).encode(),
                    validity=CERTIFICATE_VALIDITY,  # type: ignore
                )
                self.certificates.set_relation_certificate(
                    provider_certificate=ProviderCertificate(
                        relation_id=relation.id,
                        certificate=Certificate.from_string(certificate.decode()),
                        certificate_signing_request=certificate_request.certificate_signing_request,
                        ca=Certificate.from_string(root_certificate),
                        chain=[
                            Certificate.from_string(root_certificate),
                            Certificate.from_string(certificate.decode()),
                        ],
                    ),
                )
                logger.info("Certificate generated and sent to requirer")

    def _relation_created(self, relation_name: str) -> bool:
        try:
            return bool(self.model.relations[relation_name])
        except KeyError:
            return False

    def _get_root_certificate(self) -> tuple[str | None, str | None]:
        try:
            secret = self.model.get_secret(label="ca-certificate")
            secret_content = secret.get_content(refresh=True)
            return secret_content.get("ca-certificate", None), secret_content.get(
                "private-key", None
            )
        except SecretNotFoundError:
            return None, None

    def _generate_root_certificates(self) -> None:
        private_key = generate_private_key()
        ca_certificate = generate_ca(private_key=private_key, subject=CA_COMMON_NAME)
        self.unit.add_secret(
            {"private-key": private_key.decode(), "ca-certificate": ca_certificate.decode()},
            label="ca-certificate",
        )
        logger.info("Root certificates generated and stored.")


if __name__ == "__main__":
    main(DummyTLSCertificatesProviderCharm)
