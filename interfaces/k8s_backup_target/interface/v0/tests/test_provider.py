# Copyright 2026 Canonical
# See LICENSE file for licensing details.

from interface_tester import Tester
from scenario import State


def test_data_on_created():
    t = Tester(State(leader=True))
    state_out = t.run("k8s-backup-target-relation-created")
    t.assert_schema_valid()


def test_data_on_joined():
    t = Tester(State(leader=True))
    state_out = t.run("k8s-backup-target-relation-joined")
    t.assert_schema_valid()


def test_data_on_changed():
    t = Tester(State(leader=True))
    state_out = t.run("k8s-backup-target-relation-changed")
    t.assert_schema_valid()
