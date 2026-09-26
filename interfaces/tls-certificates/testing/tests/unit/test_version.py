# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing


def test_versions_match():
    """Lockstep versioning, per OP077. Also enforced repo-wide by CI."""
    assert tls_certificates_testing.__version__ == tls_certificates.__version__
