#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, cast

from ops import main
from ops.charm import ActionEvent, CharmBase, CollectStatusEvent
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charmlibs.interfaces.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    TLSCertificatesRequiresV4,
)


class DummyTLSCertificatesRequirerCharm(CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self._certificate_request = None
        self._app_request = None
        self._unit_request = None

        mode = self._get_mode()
        if hasattr(Mode, "APP_AND_UNIT") and mode == Mode.APP_AND_UNIT:
            self._app_request = self._get_app_certificate_request()
            self._unit_request = self._get_unit_certificate_request()
            self.certificates = TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="certificates",
                certificate_requests_by_mode={
                    Mode.APP: [self._app_request],
                    Mode.UNIT: [self._unit_request],
                },
                mode=mode,
                refresh_events=[
                    self.on.config_changed,
                    self.on.leader_elected,
                    self.on.certificates_relation_joined,
                ],
            )
        else:
            self._certificate_request = self._get_certificate_request()
            self.certificates = TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="certificates",
                certificate_requests=[self._certificate_request],
                mode=mode,
                refresh_events=[self.on.config_changed],
            )
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        self.framework.observe(self.on.get_certificate_action, self._on_get_certificate_action)
        self.framework.observe(
            self.on.get_app_certificate_action, self._on_get_app_certificate_action
        )
        self.framework.observe(
            self.on.get_unit_certificate_action, self._on_get_unit_certificate_action
        )
        self.framework.observe(self.on.renew_certificate_action, self._on_renew_certificate_action)

    def _on_renew_certificate_action(self, event: ActionEvent) -> None:
        if self._certificate_request is None:
            event.fail(
                "This action is not supported in APP_AND_UNIT mode. Use get-app-certificate or get-unit-certificate instead."
            )
            return
        cert, _private_key = self.certificates.get_assigned_certificate(self._certificate_request)
        if not cert:
            event.fail("Certificate not available")
            return
        self.certificates.renew_certificate(cert)

    def _on_collect_unit_status(self, event: CollectStatusEvent):
        if not self._relation_created("certificates"):
            event.add_status(BlockedStatus("Missing relation to certificates provider"))
            return
        mode = self.certificates.mode
        if hasattr(Mode, "APP_AND_UNIT") and mode == Mode.APP_AND_UNIT:
            assert self._app_request is not None
            assert self._unit_request is not None
            app_cert, _ = self.certificates.get_assigned_certificate(
                certificate_request=self._app_request
            )
            unit_cert, _ = self.certificates.get_assigned_certificate(
                certificate_request=self._unit_request
            )
            if not app_cert or not unit_cert:
                event.add_status(WaitingStatus("Waiting for certificates"))
                return
        else:
            assert self._certificate_request is not None
            cert, _ = self.certificates.get_assigned_certificate(
                certificate_request=self._certificate_request
            )
            if not cert:
                event.add_status(WaitingStatus("Waiting for certificate"))
                return
        event.add_status(ActiveStatus())

    def _on_get_certificate_action(self, event: ActionEvent) -> None:
        if self._certificate_request is None:
            event.fail(
                "This action is not supported in APP_AND_UNIT mode. Use get-app-certificate or get-unit-certificate instead."
            )
            return
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

    def _on_get_app_certificate_action(self, event: ActionEvent) -> None:
        assert self._app_request is not None
        certificate, _ = self.certificates.get_assigned_certificate(
            certificate_request=self._app_request
        )
        if not certificate:
            event.fail("App certificate not available")
            return
        event.set_results({
            "certificate": str(certificate.certificate),
            "ca": str(certificate.ca),
            "chain": str(certificate.chain),
        })

    def _on_get_unit_certificate_action(self, event: ActionEvent) -> None:
        assert self._unit_request is not None
        certificate, _ = self.certificates.get_assigned_certificate(
            certificate_request=self._unit_request
        )
        if not certificate:
            event.fail("Unit certificate not available")
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
        elif mode_config == "app_and_unit":
            if hasattr(Mode, "APP_AND_UNIT"):
                return Mode.APP_AND_UNIT
            else:
                return Mode.UNIT
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

    def _get_app_certificate_request(self) -> CertificateRequestAttributes:
        return CertificateRequestAttributes(
            common_name=self._get_config_common_name() + "-app",
            sans_dns=self._get_config_sans_dns(),
            organization=self._get_config_organization_name(),
            organizational_unit=self._get_config_organization_unit_name(),
            email_address=self._get_config_email_address(),
            country_name=self._get_config_country_name(),
            state_or_province_name=self._get_config_state_or_province_name(),
            locality_name=self._get_config_locality_name(),
        )

    def _get_unit_certificate_request(self) -> CertificateRequestAttributes:
        return CertificateRequestAttributes(
            common_name=self._get_config_common_name() + "-unit",
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
    main(DummyTLSCertificatesRequirerCharm)
