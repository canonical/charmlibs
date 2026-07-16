#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Requirer charm built on the Charmhub-hosted v4 lib, for upgrade integration tests.

This charm is packed with ``charms.tls_certificates_interface.v4.tls_certificates``
fetched from Charmhub (see pack.sh), at two pinned versions:

- fetch-lib-pre-fix: libpatch 26, from before APP mode private keys were stored
  as app-owned secrets (https://github.com/canonical/charmlibs/pull/267).
- fetch-lib-latest: the newest libpatch, which stores APP mode private keys
  app-owned but under the label this library now treats as legacy.

Upgrade tests deploy this charm, then refresh to the local charm built on the
current library, to validate that existing deployments keep their private key
and certificate (https://github.com/canonical/charmlibs/issues/565).

The certificate request construction must stay identical to charm.py so that
the CSR created by this charm still matches the request the local charm makes
after the refresh.
"""

from typing import Any, cast

from ops import main
from ops.charm import ActionEvent, CharmBase, CollectStatusEvent
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charms.tls_certificates_interface.v4.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    TLSCertificatesRequiresV4,
)


class FetchLibTLSCertificatesRequirerCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self._certificate_request = self._get_certificate_request()
        self.certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=[self._certificate_request],
            mode=self._get_mode(),
            refresh_events=[self.on.config_changed],
        )
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        self.framework.observe(self.on.get_certificate_action, self._on_get_certificate_action)

    def _on_collect_unit_status(self, event: CollectStatusEvent):
        if not self._relation_created("certificates"):
            event.add_status(BlockedStatus("Missing relation to certificates provider"))
            return
        cert, _ = self.certificates.get_assigned_certificate(
            certificate_request=self._certificate_request
        )
        if not cert:
            event.add_status(WaitingStatus("Waiting for certificate"))
            return
        event.add_status(ActiveStatus())

    def _on_get_certificate_action(self, event: ActionEvent) -> None:
        certificate, _ = self.certificates.get_assigned_certificate(
            certificate_request=self._certificate_request
        )
        if not certificate:
            event.fail("Certificate not available")
            return
        event.set_results({
            "certificate": str(certificate.certificate),
            "ca": str(certificate.ca),
            "chain": str(certificate.chain),
        })

    def _relation_created(self, relation_name: str) -> bool:
        try:
            if self.model.get_relation(relation_name):
                return True
            return False
        except KeyError:
            return False

    def _get_mode(self) -> Mode:
        mode_config = cast("str", self.model.config.get("mode", "unit"))
        if mode_config == "app":
            return Mode.APP
        return Mode.UNIT

    def _get_certificate_request(self) -> CertificateRequestAttributes:
        return CertificateRequestAttributes(
            common_name=self._get_config_common_name(),
            sans_dns=self._get_config_sans_dns(),
            organization=self._get_config_organization_name(),
            organizational_unit=self._get_config_organization_unit_name(),
            email_address=self._get_config_email_address(),
            country_name=self._get_config_country_name(),
            state_or_province_name=self._get_config_state_or_province_name(),
            locality_name=self._get_config_locality_name(),
        )

    def _get_config_common_name(self) -> str:
        common_name = self.model.config.get("common_name")
        return str(common_name) if common_name is not None else "default"

    def _get_config_sans_dns(self) -> frozenset[str]:
        config_sans_dns = cast("str", self.model.config.get("sans_dns", ""))
        return frozenset(config_sans_dns.split(",") if config_sans_dns else [])

    def _get_config_organization_name(self) -> str | None:
        return cast("str", self.model.config.get("organization_name"))

    def _get_config_organization_unit_name(self) -> str | None:
        return cast("str", self.model.config.get("organization_unit_name"))

    def _get_config_email_address(self) -> str | None:
        return cast("str", self.model.config.get("email_address"))

    def _get_config_country_name(self) -> str | None:
        return cast("str", self.model.config.get("country_name"))

    def _get_config_state_or_province_name(self) -> str | None:
        return cast("str", self.model.config.get("state_or_province_name"))

    def _get_config_locality_name(self) -> str | None:
        return cast("str", self.model.config.get("locality_name"))


if __name__ == "__main__":
    main(FetchLibTLSCertificatesRequirerCharm)
