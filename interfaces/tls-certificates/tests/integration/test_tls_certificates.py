#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

import logging
import pathlib
import time

import pytest
from pytest_operator.plugin import OpsTest

from certificates import Certificate

logger = logging.getLogger(__name__)


PACKED_DIR = pathlib.Path(__file__).parent / ".packed"
REQUIRER_LOCAL = PACKED_DIR / "requirer-local.charm"
REQUIRER_PUBLISHED = PACKED_DIR / "requirer-published.charm"
PROVIDER_LOCAL = PACKED_DIR / "provider-local.charm"
PROVIDER_PUBLISHED = PACKED_DIR / "provider-published.charm"
TLS_CERTIFICATES_PROVIDER_APP_NAME = "tls-certificates-provider"
TLS_CERTIFICATES_REQUIRER_APP_NAME = "tls-certificates-requirer"


class TestIntegration:
    @pytest.mark.upgrade
    async def test_given_main_deployed_when_upgraded_then_certs_are_retrieved(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        requirer_app_name = f"{TLS_CERTIFICATES_REQUIRER_APP_NAME}-upgrade"
        provider_app_name = f"{TLS_CERTIFICATES_PROVIDER_APP_NAME}-upgrade"

        await ops_test.model.deploy(
            REQUIRER_PUBLISHED,
            application_name=requirer_app_name,
            series="jammy",
        )
        await ops_test.model.deploy(
            PROVIDER_PUBLISHED,
            application_name=provider_app_name,
            series="jammy",
        )
        # create a relation to requests certs
        await ops_test.model.add_relation(
            relation1=requirer_app_name,
            relation2=provider_app_name,
        )

        await ops_test.model.wait_for_idle(
            apps=[requirer_app_name, provider_app_name],
            status="active",
            timeout=1000,
        )
        # retrieve certs and validate
        requirer_unit = ops_test.model.units[f"{requirer_app_name}/0"]
        assert requirer_unit

        action = await requirer_unit.run_action(action_name="get-certificate")

        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None

        # upgrade to the new version of the lib
        await ops_test.model.applications[requirer_app_name].refresh(
            path=REQUIRER_LOCAL,
        )

        await ops_test.model.applications[provider_app_name].refresh(
            path=PROVIDER_LOCAL,
        )
        await ops_test.model.wait_for_idle(
            apps=[requirer_app_name, provider_app_name],
            status="active",
            timeout=1000,
        )

        # renew the certificate
        action = await requirer_unit.run_action(action_name="renew-certificate")
        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        await ops_test.model.wait_for_idle(
            apps=[requirer_app_name, provider_app_name],
            status="active",
            timeout=1000,
        )
        # retrieve certs and validate
        requirer_unit = ops_test.model.units[f"{requirer_app_name}/0"]
        assert requirer_unit

        action = await requirer_unit.run_action(action_name="get-certificate")

        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None

        # tear down so that the rest of the tests can run as normal
        await ops_test.model.applications[requirer_app_name].remove()
        await ops_test.model.applications[provider_app_name].remove()

    async def test_given_charms_packed_when_deploy_charm_then_status_is_blocked(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        await ops_test.model.deploy(
            REQUIRER_LOCAL,
            application_name=TLS_CERTIFICATES_REQUIRER_APP_NAME,
            series="jammy",
        )
        await ops_test.model.deploy(
            PROVIDER_LOCAL,
            application_name=TLS_CERTIFICATES_PROVIDER_APP_NAME,
            series="jammy",
        )

        await ops_test.model.wait_for_idle(
            apps=[TLS_CERTIFICATES_REQUIRER_APP_NAME, TLS_CERTIFICATES_PROVIDER_APP_NAME],
            status="blocked",
            timeout=1000,
        )

    async def test_given_charms_deployed_when_relate_then_status_is_active(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        await ops_test.model.add_relation(
            relation1=TLS_CERTIFICATES_REQUIRER_APP_NAME,
            relation2=TLS_CERTIFICATES_PROVIDER_APP_NAME,
        )

        await ops_test.model.wait_for_idle(
            apps=[TLS_CERTIFICATES_REQUIRER_APP_NAME, TLS_CERTIFICATES_PROVIDER_APP_NAME],
            status="active",
            timeout=1000,
        )

    async def test_given_charms_deployed_when_relate_then_requirer_received_certs(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        requirer_unit = ops_test.model.units[f"{TLS_CERTIFICATES_REQUIRER_APP_NAME}/0"]
        assert requirer_unit

        action = await requirer_unit.run_action(action_name="get-certificate")

        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None

    async def test_given_additional_requirer_charm_deployed_when_relate_then_requirer_received_certs(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        new_requirer_app_name = "new-tls-requirer"
        await ops_test.model.deploy(
            REQUIRER_LOCAL, application_name=new_requirer_app_name, series="jammy"
        )
        await ops_test.model.add_relation(
            relation1=new_requirer_app_name,
            relation2=TLS_CERTIFICATES_PROVIDER_APP_NAME,
        )
        await ops_test.model.wait_for_idle(
            apps=[
                TLS_CERTIFICATES_PROVIDER_APP_NAME,
                new_requirer_app_name,
            ],
            status="active",
            timeout=1000,
        )
        requirer_unit = ops_test.model.units[f"{new_requirer_app_name}/0"]
        assert requirer_unit

        action = await requirer_unit.run_action(action_name="get-certificate")

        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None

    async def test_given_4_min_certificate_validity_when_certificate_expires_then_certificate_is_automatically_renewed(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        requirer_unit = ops_test.model.units[f"{TLS_CERTIFICATES_REQUIRER_APP_NAME}/0"]
        assert requirer_unit

        action = await requirer_unit.run_action(action_name="get-certificate")

        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )

        assert "certificate" in action_output and action_output["certificate"] is not None
        initial_certificate = Certificate(action_output["certificate"])

        time.sleep(300)  # Wait 5 minutes for certificate to expire

        action = await requirer_unit.run_action(action_name="get-certificate")

        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )

        assert "certificate" in action_output and action_output["certificate"] is not None
        renewed_certificate = Certificate(action_output["certificate"])

        assert initial_certificate.expiry != renewed_certificate.expiry

    async def test_given_app_and_unit_mode_when_relate_then_both_certificates_received(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        app_and_unit_requirer_app_name = "app-and-unit-requirer"
        await ops_test.model.deploy(
            REQUIRER_LOCAL,
            application_name=app_and_unit_requirer_app_name,
            series="jammy",
            config={"mode": "app_and_unit"},
        )
        await ops_test.model.add_relation(
            relation1=app_and_unit_requirer_app_name,
            relation2=TLS_CERTIFICATES_PROVIDER_APP_NAME,
        )
        await ops_test.model.wait_for_idle(
            apps=[
                TLS_CERTIFICATES_PROVIDER_APP_NAME,
                app_and_unit_requirer_app_name,
            ],
            status="active",
            timeout=1000,
        )

        requirer_unit = ops_test.model.units[f"{app_and_unit_requirer_app_name}/0"]
        assert requirer_unit

        action = await requirer_unit.run_action(action_name="get-app-certificate")
        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None
        app_certificate = Certificate(action_output["certificate"])

        action = await requirer_unit.run_action(action_name="get-unit-certificate")
        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None
        unit_certificate = Certificate(action_output["certificate"])

        assert app_certificate.common_name == "banana-app"
        assert unit_certificate.common_name == "banana-unit"

    async def test_given_app_and_unit_mode_with_multiple_units_when_scaled_then_each_unit_has_own_cert(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        app_and_unit_requirer_app_name = "app-and-unit-requirer"

        app = ops_test.model.applications[app_and_unit_requirer_app_name]
        await app.scale(2)

        await ops_test.model.wait_for_idle(
            apps=[app_and_unit_requirer_app_name],
            status="active",
            timeout=1000,
            wait_for_exact_units=2,
        )

        unit_0 = ops_test.model.units[f"{app_and_unit_requirer_app_name}/0"]
        assert unit_0

        action = await unit_0.run_action(action_name="get-app-certificate")
        app_cert_output_0 = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        app_certificate_0 = Certificate(app_cert_output_0["certificate"])

        action = await unit_0.run_action(action_name="get-unit-certificate")
        unit_cert_output_0 = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        unit_certificate_0 = Certificate(unit_cert_output_0["certificate"])

        unit_1 = ops_test.model.units[f"{app_and_unit_requirer_app_name}/1"]
        assert unit_1

        action = await unit_1.run_action(action_name="get-app-certificate")
        app_cert_output_1 = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        app_certificate_1 = Certificate(app_cert_output_1["certificate"])

        action = await unit_1.run_action(action_name="get-unit-certificate")
        unit_cert_output_1 = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        unit_certificate_1 = Certificate(unit_cert_output_1["certificate"])

        assert str(app_certificate_0.certificate) == str(app_certificate_1.certificate)

        assert str(unit_certificate_0.certificate) != str(unit_certificate_1.certificate)

    async def test_given_additional_app_and_unit_requirer_when_related_then_certificates_received(
        self, ops_test: OpsTest
    ):
        assert ops_test.model
        new_app_and_unit_requirer_app_name = "new-app-and-unit-requirer"
        await ops_test.model.deploy(
            REQUIRER_LOCAL,
            application_name=new_app_and_unit_requirer_app_name,
            series="jammy",
            config={"mode": "app_and_unit"},
        )
        await ops_test.model.add_relation(
            relation1=new_app_and_unit_requirer_app_name,
            relation2=TLS_CERTIFICATES_PROVIDER_APP_NAME,
        )
        await ops_test.model.wait_for_idle(
            apps=[
                TLS_CERTIFICATES_PROVIDER_APP_NAME,
                new_app_and_unit_requirer_app_name,
            ],
            status="active",
            timeout=1000,
        )

        requirer_unit = ops_test.model.units[f"{new_app_and_unit_requirer_app_name}/0"]
        assert requirer_unit

        action = await requirer_unit.run_action(action_name="get-app-certificate")
        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None

        action = await requirer_unit.run_action(action_name="get-unit-certificate")
        action_output = await ops_test.model.get_action_output(
            action_uuid=action.entity_id, wait=60
        )
        assert action_output["return-code"] == 0
        assert "ca" in action_output and action_output["ca"] is not None
        assert "certificate" in action_output and action_output["certificate"] is not None
        assert "chain" in action_output and action_output["chain"] is not None
