# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from charmlibs.interfaces import certificate_transfer as certificate_transfer
from charmlibs.interfaces import certificate_transfer_testing as certificate_transfer_testing


def test_versions_match():
    """Lockstep versioning, per OP077. Also enforced repo-wide by CI."""
    assert certificate_transfer_testing.__version__ == certificate_transfer.__version__
