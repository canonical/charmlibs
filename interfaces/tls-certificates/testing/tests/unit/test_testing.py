# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from ops import testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing

JUJU_NETWORK_KEYS = {"egress-subnets", "ingress-address", "private-address"}


def test_local_provider():
    rel = tls_certificates_testing.relation_for_provider("foo")
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert "certificate_signing_requests" in rel.remote_units_data[0]
    # certificates are delivered via app data unless provider=False is passed
    assert rel.local_app_data
    assert "certificates" in rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)


def test_local_provider_w_mode_app():
    rel = tls_certificates_testing.relation_for_provider("foo", mode=tls_certificates.Mode.APP)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in app mode when specified
    assert "certificate_signing_requests" in rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])
    # certificates are delivered via app data
    assert rel.local_app_data
    assert "certificates" in rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)


def test_local_provider_w_provider_false():
    rel = tls_certificates_testing.relation_for_provider("foo", provider=False)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert "certificate_signing_requests" in rel.remote_units_data[0]
    # certificates are not provided with provider=False
    assert not rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)


def test_local_requirer():
    rel = tls_certificates_testing.relation_for_requirer("foo")
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.local_app_data
    assert "certificate_signing_requests" in rel.local_unit_data
    # certificates are delivered via app data unless provider=False is passed
    assert rel.remote_app_data
    assert "certificates" in rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])


def test_local_requirer_w_mode_app():
    rel = tls_certificates_testing.relation_for_requirer("foo", mode=tls_certificates.Mode.APP)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in app mode when specified
    assert "certificate_signing_requests" in rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)
    # certificates are delivered via app data unless provider=False is passed
    assert rel.remote_app_data
    assert "certificates" in rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])


def test_local_requirer_w_provider_false():
    rel = tls_certificates_testing.relation_for_requirer("foo", provider=False)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.local_app_data
    assert "certificate_signing_requests" in rel.local_unit_data
    # certificates are not provided with provider=False
    assert not rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])
