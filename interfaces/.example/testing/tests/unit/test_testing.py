# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from ops import testing

from charmlibs.interfaces import example_interface as example_interface
from charmlibs.interfaces import example_interface_testing as example_interface_testing


def test_local_provider():
    rel = example_interface_testing.relation_for_provider('foo')
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == 'foo'
    assert rel.interface == 'example-interface'


def test_local_requirer():
    rel = example_interface_testing.relation_for_requirer('bar')
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == 'bar'
    assert rel.interface == 'example-interface'
