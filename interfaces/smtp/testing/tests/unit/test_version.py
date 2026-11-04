# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


from charmlibs.interfaces import smtp as smtp
from charmlibs.interfaces import smtp_testing as smtp_testing


def test_versions_match():
    assert smtp_testing.__version__ == smtp.__version__
