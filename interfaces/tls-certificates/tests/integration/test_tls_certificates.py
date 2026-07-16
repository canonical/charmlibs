#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import json
import logging
import pathlib
import time
from datetime import timedelta

import jubilant
import pytest

from certificates import Certificate
from charmlibs.interfaces import tls_certificates

logger = logging.getLogger(__name__)


PACKED_DIR = pathlib.Path(__file__).parent / ".packed"
REQUIRER_LOCAL = PACKED_DIR / "requirer-local.charm"
REQUIRER_PUBLISHED = PACKED_DIR / "requirer-published.charm"
REQUIRER_FETCH_LIB_LATEST = PACKED_DIR / "requirer-fetch-lib-latest.charm"
REQUIRER_FETCH_LIB_PRE_FIX = PACKED_DIR / "requirer-fetch-lib-pre-fix.charm"
PROVIDER_LOCAL = PACKED_DIR / "provider-local.charm"
PROVIDER_PUBLISHED = PACKED_DIR / "provider-published.charm"
TLS_CERTIFICATES_PROVIDER_APP_NAME = "tls-certificates-provider"
TLS_CERTIFICATES_REQUIRER_APP_NAME = "tls-certificates-requirer"


def _assert_certificate_fields(task: jubilant.Task):
    """Assert that the action task contains valid certificate fields."""
    assert "ca" in task.results and task.results["ca"] is not None
    assert "certificate" in task.results and task.results["certificate"] is not None
    assert "chain" in task.results and task.results["chain"] is not None


def _base64(pem: str) -> str:
    return base64.b64encode(pem.encode()).decode()


def _get_outstanding_csrs(juju: jubilant.Juju, manual_tls_unit: str) -> list[str]:
    """Return the CSRs the manual-tls-certificates charm has not signed yet."""
    try:
        task = juju.run(manual_tls_unit, "get-outstanding-certificate-requests")
    except jubilant.TaskError:
        return []
    return [request["csr"] for request in json.loads(task.results.get("result", "[]"))]


def _wait_for_outstanding_csr(juju: jubilant.Juju, manual_tls_unit: str) -> str:
    timeout = time.time() + 600
    while time.time() < timeout:
        csrs = _get_outstanding_csrs(juju, manual_tls_unit)
        if csrs:
            return csrs[0]
        time.sleep(10)
    raise TimeoutError(f"No outstanding certificate request appeared on {manual_tls_unit}")


def _sign_csr(csr_str: str) -> tuple[str, str]:
    """Sign a CSR with a locally generated CA, returning (certificate, ca_certificate) PEMs."""
    ca_private_key = tls_certificates.PrivateKey.generate()
    ca = tls_certificates.Certificate.generate_self_signed_ca(
        attributes=tls_certificates.CertificateRequestAttributes(
            common_name="integration-test-ca", is_ca=True
        ),
        private_key=ca_private_key,
        validity=timedelta(days=365),
    )
    certificate = tls_certificates.Certificate.generate(
        csr=tls_certificates.CertificateSigningRequest.from_string(csr_str),
        ca=ca,
        ca_private_key=ca_private_key,
        validity=timedelta(days=365),
    )
    return str(certificate), str(ca)


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

    @pytest.mark.upgrade
    @pytest.mark.parametrize(
        "legacy_charm",
        [
            pytest.param(REQUIRER_FETCH_LIB_PRE_FIX, id="pre-app-owned-key-fix"),
            pytest.param(REQUIRER_FETCH_LIB_LATEST, id="latest-charmhub-lib"),
        ],
    )
    def test_given_charmhub_lib_app_mode_deployment_when_upgraded_then_certificate_is_preserved(
        self, juju: jubilant.Juju, legacy_charm: pathlib.Path
    ):
        """Upgrading an APP mode deployment must not regenerate the key, CSR, or certificate.

        Deployments made with the Charmhub v4 lib store the APP mode private key
        under a label this library treats as legacy, either unit-owned (before
        the fix in https://github.com/canonical/charmlibs/pull/267) or app-owned
        (after it). On refresh, the library must migrate that key instead of
        generating a new one (https://github.com/canonical/charmlibs/issues/565).

        The provider is manual-tls-certificates, which only signs CSRs through
        operator actions. If the refresh regenerated the key, its CSR would be
        replaced and never signed, so the requirer could not be active with its
        original certificate afterwards.
        """
        requirer_app_name = legacy_charm.stem
        provider_app_name = f"{requirer_app_name}-provider"
        requirer_unit = f"{requirer_app_name}/0"
        provider_unit = f"{provider_app_name}/0"

        juju.deploy(
            legacy_charm,
            app=requirer_app_name,
            base="ubuntu@22.04",
            config={"mode": "app"},
        )
        juju.deploy(
            "manual-tls-certificates",
            app=provider_app_name,
            channel="1/stable",
            base="ubuntu@24.04",
        )
        juju.integrate(requirer_app_name, provider_app_name)
        juju.wait(
            lambda status: jubilant.all_agents_idle(status, requirer_app_name, provider_app_name),
            timeout=1000,
        )

        # sign the requirer's CSR and provide the certificate manually
        csr = _wait_for_outstanding_csr(juju, provider_unit)
        certificate, ca_certificate = _sign_csr(csr)
        juju.run(
            provider_unit,
            "provide-certificate",
            {
                "certificate-signing-request": _base64(csr),
                "certificate": _base64(certificate),
                "ca-certificate": _base64(ca_certificate),
                "ca-chain": _base64(ca_certificate),
            },
        )
        juju.wait(
            lambda status: (
                jubilant.all_active(status, requirer_app_name, provider_app_name)
                and jubilant.all_agents_idle(status, requirer_app_name, provider_app_name)
            ),
            timeout=1000,
        )
        task = juju.run(requirer_unit, "get-certificate")
        _assert_certificate_fields(task)
        certificate_before_upgrade = task.results["certificate"]

        # upgrade to the local charm built on the current library
        juju.refresh(requirer_app_name, path=REQUIRER_LOCAL)
        juju.wait(
            lambda status: (
                jubilant.all_active(status, requirer_app_name)
                and jubilant.all_agents_idle(status, requirer_app_name)
            ),
            timeout=1000,
        )

        # the certificate survived the upgrade and no new CSR was requested
        task = juju.run(requirer_unit, "get-certificate")
        _assert_certificate_fields(task)
        assert task.results["certificate"] == certificate_before_upgrade
        assert not _get_outstanding_csrs(juju, provider_unit)

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


class TestProviderCapabilitiesUpgrade:
    """Verify capability advertisement does not break cross-version compatibility."""

    @pytest.mark.upgrade
    def test_given_provider_supports_capabilities_and_requirer_does_not_when_related_then_requirer_gets_certs(
        self, juju: jubilant.Juju
    ):
        """A capability-advertising provider works with a legacy requirer (no capability key)."""
        requirer_app_name = "old-requirer-new-provider-req"
        provider_app_name = "old-requirer-new-provider-prov"

        juju.deploy(REQUIRER_PUBLISHED, app=requirer_app_name, base="ubuntu@22.04")
        juju.deploy(PROVIDER_LOCAL, app=provider_app_name, base="ubuntu@22.04")
        juju.integrate(requirer_app_name, provider_app_name)
        juju.wait(
            lambda status: jubilant.all_active(status, requirer_app_name, provider_app_name),
            timeout=1000,
        )

        task = juju.run(f"{requirer_app_name}/0", "get-certificate")
        _assert_certificate_fields(task)

        juju.remove_application(requirer_app_name, provider_app_name)

    @pytest.mark.upgrade
    def test_given_requirer_supports_capabilities_and_provider_does_not_when_related_then_capabilities_unavailable(
        self, juju: jubilant.Juju
    ):
        """A new requirer reports capabilities unavailable for a legacy provider but still works."""
        requirer_app_name = "new-requirer-old-provider-req"
        provider_app_name = "new-requirer-old-provider-prov"

        juju.deploy(REQUIRER_LOCAL, app=requirer_app_name, base="ubuntu@22.04")
        juju.deploy(PROVIDER_PUBLISHED, app=provider_app_name, base="ubuntu@22.04")
        juju.integrate(requirer_app_name, provider_app_name)
        juju.wait(
            lambda status: jubilant.all_active(status, requirer_app_name, provider_app_name),
            timeout=1000,
        )

        task = juju.run(f"{requirer_app_name}/0", "get-certificate")
        _assert_certificate_fields(task)

        task = juju.run(f"{requirer_app_name}/0", "get-provider-capabilities")
        assert task.results.get("available") == "false"

        juju.remove_application(requirer_app_name, provider_app_name)
