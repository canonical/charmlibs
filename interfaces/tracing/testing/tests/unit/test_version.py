# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from charmlibs.interfaces import tracing as tracing
from charmlibs.interfaces import tracing_testing as tracing_testing


def test_versions_match():
    """Lockstep versioning, per OP077. Also enforced repo-wide by CI."""
    assert tracing_testing.__version__ == tracing.__version__
