#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import pathlib
import time

import jubilant
import pytest

from certificates import Certificate

logger = logging.getLogger(__name__)


PACKED_DIR = pathlib.Path(__file__).parent / ".packed"
REQUIRER_LOCAL = PACKED_DIR / "requirer-local.charm"
REQUIRER_PUBLISHED = PACKED_DIR / "requirer-published.charm"
PROVIDER_LOCAL = PACKED_DIR / "provider-local.charm"
PROVIDER_PUBLISHED = PACKED_DIR / "provider-published.charm"
TLS_CERTIFICATES_PROVIDER_APP_NAME = "tls-certificates-provider"
TLS_CERTIFICATES_REQUIRER_APP_NAME = "tls-certificates-requirer"


def _assert_certificate_fields(task: jubilant.Task):
    """Assert that the action task contains valid certificate fields."""
    assert "ca" in task.results and task.results["ca"] is not None
    assert "certificate" in task.results and task.results["certificate"] is not None
    assert "chain" in task.results and task.results["chain"] is not None


class TestIntegration:
    @pytest.mark.upgrade
    def test_given_main_deployed_when_upgraded_then_certs_are_retrieved(self, juju: jubilant.Juju):
        requirer_app_name = f"{TLS_CERTIFICATES_REQUIRER_APP_NAME}-upgrade"
        provider_app_name = f"{TLS_CERTIFICATES_PROVIDER_APP_NAME}-upgrade"

        juju.deploy(
            REQUIRER_PUBLISHED,
            app=requirer_app_name,
            base="ubuntu@22.04",
        )
        juju.deploy(
            PROVIDER_PUBLISHED,
            app=provider_app_name,
            base="ubuntu@22.04",
        )
        # create a relation to request certs
        juju.integrate(requirer_app_name, provider_app_name)

        juju.wait(
            lambda status: jubilant.all_active(status, requirer_app_name, provider_app_name),
            timeout=1000,
        )
        # retrieve certs and validate
        task = juju.run(f"{requirer_app_name}/0", "get-certificate")
        _assert_certificate_fields(task)

        # upgrade to the new version of the lib
        juju.refresh(requirer_app_name, path=REQUIRER_LOCAL)
        juju.refresh(provider_app_name, path=PROVIDER_LOCAL)
        juju.wait(
            lambda status: jubilant.all_active(status, requirer_app_name, provider_app_name),
            timeout=1000,
        )

        # renew the certificate
        juju.run(f"{requirer_app_name}/0", "renew-certificate")
        juju.wait(
            lambda status: jubilant.all_active(status, requirer_app_name, provider_app_name),
            timeout=1000,
        )
        # retrieve certs and validate
        task = juju.run(f"{requirer_app_name}/0", "get-certificate")
        _assert_certificate_fields(task)

        # tear down so that the rest of the tests can run as normal
        juju.remove_application(requirer_app_name, provider_app_name)

    def test_given_charms_packed_when_deploy_charm_then_status_is_blocked(
        self, juju: jubilant.Juju
    ):
        juju.deploy(
            REQUIRER_LOCAL,
            app=TLS_CERTIFICATES_REQUIRER_APP_NAME,
            base="ubuntu@22.04",
        )
        juju.deploy(
            PROVIDER_LOCAL,
            app=TLS_CERTIFICATES_PROVIDER_APP_NAME,
            base="ubuntu@22.04",
        )

        juju.wait(
            lambda status: jubilant.all_blocked(
                status, TLS_CERTIFICATES_REQUIRER_APP_NAME, TLS_CERTIFICATES_PROVIDER_APP_NAME
            ),
            timeout=1000,
        )

    def test_given_charms_deployed_when_relate_then_status_is_active(self, juju: jubilant.Juju):
        juju.integrate(
            TLS_CERTIFICATES_REQUIRER_APP_NAME,
            TLS_CERTIFICATES_PROVIDER_APP_NAME,
        )

        juju.wait(
            lambda status: jubilant.all_active(
                status, TLS_CERTIFICATES_REQUIRER_APP_NAME, TLS_CERTIFICATES_PROVIDER_APP_NAME
            ),
            timeout=1000,
        )

    def test_given_charms_deployed_when_relate_then_requirer_received_certs(
        self, juju: jubilant.Juju
    ):
        task = juju.run(f"{TLS_CERTIFICATES_REQUIRER_APP_NAME}/0", "get-certificate")
        _assert_certificate_fields(task)

    def test_given_additional_requirer_charm_deployed_when_relate_then_requirer_received_certs(
        self, juju: jubilant.Juju
    ):
        new_requirer_app_name = "new-tls-requirer"
        juju.deploy(REQUIRER_LOCAL, app=new_requirer_app_name, base="ubuntu@22.04")
        juju.integrate(new_requirer_app_name, TLS_CERTIFICATES_PROVIDER_APP_NAME)
        juju.wait(
            lambda status: jubilant.all_active(
                status, TLS_CERTIFICATES_PROVIDER_APP_NAME, new_requirer_app_name
            ),
            timeout=1000,
        )

        task = juju.run(f"{new_requirer_app_name}/0", "get-certificate")
        _assert_certificate_fields(task)

    def test_given_4_min_certificate_validity_when_certificate_expires_then_certificate_is_automatically_renewed(
        self, juju: jubilant.Juju
    ):
        task = juju.run(f"{TLS_CERTIFICATES_REQUIRER_APP_NAME}/0", "get-certificate")
        assert "certificate" in task.results and task.results["certificate"] is not None
        initial_certificate = Certificate(task.results["certificate"])

        time.sleep(300)  # Wait 5 minutes for certificate to expire

        task = juju.run(f"{TLS_CERTIFICATES_REQUIRER_APP_NAME}/0", "get-certificate")
        assert "certificate" in task.results and task.results["certificate"] is not None
        renewed_certificate = Certificate(task.results["certificate"])

        assert initial_certificate.expiry != renewed_certificate.expiry

    def test_given_app_and_unit_mode_when_relate_then_both_certificates_received(
        self, juju: jubilant.Juju
    ):
        app_and_unit_requirer_app_name = "app-and-unit-requirer"
        juju.deploy(
            REQUIRER_LOCAL,
            app=app_and_unit_requirer_app_name,
            base="ubuntu@22.04",
            config={"mode": "app_and_unit"},
        )
        juju.integrate(app_and_unit_requirer_app_name, TLS_CERTIFICATES_PROVIDER_APP_NAME)
        juju.wait(
            lambda status: jubilant.all_active(
                status, TLS_CERTIFICATES_PROVIDER_APP_NAME, app_and_unit_requirer_app_name
            ),
            timeout=1000,
        )

        task = juju.run(f"{app_and_unit_requirer_app_name}/0", "get-app-certificate")
        _assert_certificate_fields(task)
        app_certificate_str = task.results["certificate"]

        task = juju.run(f"{app_and_unit_requirer_app_name}/0", "get-unit-certificate")
        _assert_certificate_fields(task)
        unit_certificate_str = task.results["certificate"]

        assert app_certificate_str != unit_certificate_str

    def test_given_additional_app_and_unit_requirer_when_related_then_certificates_received(
        self, juju: jubilant.Juju
    ):
        new_app_and_unit_requirer_app_name = "new-app-and-unit-requirer"
        juju.deploy(
            REQUIRER_LOCAL,
            app=new_app_and_unit_requirer_app_name,
            base="ubuntu@22.04",
            config={"mode": "app_and_unit"},
        )
        juju.integrate(new_app_and_unit_requirer_app_name, TLS_CERTIFICATES_PROVIDER_APP_NAME)
        juju.wait(
            lambda status: jubilant.all_active(
                status, TLS_CERTIFICATES_PROVIDER_APP_NAME, new_app_and_unit_requirer_app_name
            ),
            timeout=1000,
        )

        task = juju.run(f"{new_app_and_unit_requirer_app_name}/0", "get-app-certificate")
        _assert_certificate_fields(task)

        task = juju.run(f"{new_app_and_unit_requirer_app_name}/0", "get-unit-certificate")
        _assert_certificate_fields(task)
