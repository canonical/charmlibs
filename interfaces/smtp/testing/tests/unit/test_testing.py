# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from ops import testing

from charmlibs.interfaces import smtp as smtp
from charmlibs.interfaces import smtp_testing as smtp_testing


def test_local_provider():
    rel = smtp_testing.relation_for_provider('foo')
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == 'foo'
    assert rel.interface == 'smtp'


def test_local_requirer():
    rel = smtp_testing.relation_for_requirer('bar')
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == 'bar'
    assert rel.interface == 'smtp'
