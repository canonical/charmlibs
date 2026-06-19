# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


from charmlibs.interfaces import example_interface as example_interface
from charmlibs.interfaces import example_interface_testing as example_interface_testing


def test_versions_match():
    assert example_interface_testing.__version__ == example_interface.__version__
