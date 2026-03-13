# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing


def test_versions_match():
    assert tls_certificates_testing.__version__ == tls_certificates.__version__
