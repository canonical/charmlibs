# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import dataclasses
import json
from typing import Any

import ops
import pytest
import scenario

from charmlibs.interfaces.certificate_transfer import (
    CertificatesAvailableEvent,
    CertificatesRemovedEvent,
    CertificateTransferRequires,
)

STORED_STATE_OWNER = (
    "DummyCertificateTransferRequirerCharm/CertificateTransferRequires[certificate_transfer_v1]"
)


class DummyCertificateTransferRequirerCharm(ops.CharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.certificate_transfer = CertificateTransferRequires(self, "certificate_transfer")
        self.framework.observe(
            self.on.get_all_certificates_action, self._on_get_all_certificates_action
        )
        self.framework.observe(self.on.is_ready_action, self._on_is_ready_action)
        self.framework.observe(self.on.update_status, self._on_update_status)

    def _on_get_all_certificates_action(self, event: ops.ActionEvent):
        relation_id = event.params.get("relation-id", None)
        certificates = self.certificate_transfer.get_all_certificates(
            relation_id=int(relation_id) if relation_id else None
        )
        event.set_results({"certificates": certificates})

    def _on_is_ready_action(self, event: ops.ActionEvent):
        relation_id = event.params.get("relation-id", None)
        assert relation_id
        relation = self.model.get_relation(
            relation_name="certificate_transfer", relation_id=int(relation_id)
        )
        assert relation
        is_ready = self.certificate_transfer.is_ready(relation)
        event.set_results({"is-ready": is_ready})

    def _on_update_status(self, _: Any):
        if self.certificate_transfer.get_all_certificates():
            self.unit.status = ops.ActiveStatus()
        else:
            self.unit.status = ops.WaitingStatus()


class TestCertificateTransferRequiresV1:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = scenario.Context(
            charm_type=DummyCertificateTransferRequirerCharm,
            meta={
                "name": "certificate-transfer-requirer",
                "requires": {"certificate_transfer": {"interface": "certificate_transfer"}},
            },
            actions={
                "get-all-certificates": {
                    "params": {
                        "relation-id": {"type": "string"},
                    },
                },
                "is-ready": {
                    "params": {
                        "relation-id": {"type": "string"},
                    },
                },
            },
        )

    def test_given_is_leader_when_relation_created_then_version_number_is_added_to_app_databag(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        state_out = self.ctx.run(self.ctx.on.relation_created(relation), state_in)

        relation = state_out.get_relations("certificate_transfer")[0]

        assert relation.local_app_data["version"] == "1"

    def test_given_is_not_leader_when_relation_created_then_debug_message_is_logged(
        self,
        caplog: pytest.LogCaptureFixture,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
        )
        state_in = scenario.State(leader=False, relations=[relation])

        self.ctx.run(self.ctx.on.relation_created(relation), state_in)

        logs = [(record.levelname, record.module, record.message) for record in caplog.records]
        assert (
            "DEBUG",
            "_certificate_transfer",
            "Only leader unit sets the version number in the app databag",
        ) in logs

    def test_given_certificates_in_relation_data_when_relation_changed_then_certificate_available_event_is_emitted(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        state_in = scenario.State(relations=[relation])

        self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        assert len(self.ctx.emitted_events) == 2
        assert isinstance(self.ctx.emitted_events[1], CertificatesAvailableEvent)
        assert self.ctx.emitted_events[1].certificates == {"cert1"}
        assert self.ctx.emitted_events[1].relation_id == relation.id

    def test_given_relation_created_with_no_remote_units_when_update_status_then_no_crash(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_units_data={},
        )
        state_in = scenario.State(relations=[relation])

        state_out = self.ctx.run(self.ctx.on.update_status(), state_in)

        assert state_out.unit_status == scenario.WaitingStatus()

    def test_given_certificates_in_relation_data_in_v0_when_relation_changed_then_certificate_available_event_is_emitted(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_units_data={
                0: {
                    "certificate": json.dumps("cert1"),
                    "ca": json.dumps("cert1"),
                    "chain": json.dumps(["cert1"]),
                    "version": json.dumps(0),
                }
            },
        )
        state_in = scenario.State(relations=[relation])

        self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        assert len(self.ctx.emitted_events) == 2
        assert isinstance(self.ctx.emitted_events[1], CertificatesAvailableEvent)
        assert self.ctx.emitted_events[1].certificates == {"cert1"}
        assert self.ctx.emitted_events[1].relation_id == relation.id

    def test_given_empty_v1_app_databag_and_v0_unit_data_when_read_repeatedly_then_empty_set_is_returned(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"version": "1", "certificates": json.dumps([])},
            remote_units_data={
                0: {
                    "certificate": json.dumps("cert1"),
                    "ca": json.dumps("cert1"),
                    "chain": json.dumps(["cert1"]),
                    "version": json.dumps(0),
                }
            },
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(
            self.ctx.on.action("is-ready", params={"relation-id": str(relation.id)}),
            state_in,
        ) as manager:
            charm = manager.charm
            first_read = charm.certificate_transfer.get_all_certificates(relation.id)
            second_read = charm.certificate_transfer.get_all_certificates(relation.id)

        assert first_read == set()
        assert second_read == set()

    def test_given_v0_unit_data_when_read_repeatedly_then_relation_units_are_not_mutated(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_units_data={
                0: {
                    "certificate": json.dumps("cert1"),
                    "ca": json.dumps("cert1"),
                    "chain": json.dumps(["cert1"]),
                    "version": json.dumps(0),
                },
                1: {
                    "certificate": json.dumps("cert2"),
                    "ca": json.dumps("cert2"),
                    "chain": json.dumps(["cert2"]),
                    "version": json.dumps(0),
                },
            },
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(
            self.ctx.on.action("is-ready", params={"relation-id": str(relation.id)}),
            state_in,
        ) as manager:
            charm = manager.charm
            remote_relation = charm.model.get_relation("certificate_transfer", relation.id)
            assert remote_relation is not None
            units_before = set(remote_relation.units)
            first_read = charm.certificate_transfer.get_all_certificates(relation.id)
            second_read = charm.certificate_transfer.get_all_certificates(relation.id)

            assert set(remote_relation.units) == units_before

        assert first_read == second_read
        assert first_read in ({"cert1"}, {"cert2"})

    def test_given_none_of_the_expected_keys_in_relation_data_when_relation_changed_then_certificate_available_event_emitted_with_empty_cert(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"bad-key": json.dumps(["cert1"])},
        )
        state_in = scenario.State(relations=[relation])

        self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        assert len(self.ctx.emitted_events) == 2
        assert isinstance(self.ctx.emitted_events[1], CertificatesAvailableEvent)
        assert self.ctx.emitted_events[1].certificates == set()
        assert self.ctx.emitted_events[1].relation_id == relation.id

    def test_given_certificates_in_relation_data_when_relation_removed_then_certificates_removed_event_is_emitted(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        state_in = scenario.State(relations=[relation])

        self.ctx.run(self.ctx.on.relation_broken(relation), state_in)

        assert len(self.ctx.emitted_events) == 2
        assert isinstance(self.ctx.emitted_events[1], CertificatesRemovedEvent)
        assert self.ctx.emitted_events[1].relation_id == relation.id

    def test_given_no_relation_available_when_get_all_certificates_then_empty_set_returned(self):
        state_in = scenario.State()

        self.ctx.run(
            self.ctx.on.action("get-all-certificates"),
            state_in,
        )

        assert self.ctx.action_results == {"certificates": set()}

    @pytest.mark.parametrize(
        "databag_value,error_msg",
        [
            (
                '"some string"',
                """('Error parsing relation databag: ('failed to validate databag: \
{\\'certificates\\': \\'"some string"\\'}',). ', 'Make sure not to interact with the\
 databags except using the public methods in the provider library and use version V1.')""",
            ),
            (
                "unloadable",
                """('Error parsing relation databag: ("invalid databag contents: \
expecting json. {'certificates': 'unloadable'}",). ', 'Make sure not to interact with \
the databags except using the public methods in the provider library and use version V1.')""",
            ),
        ],
    )
    def test_given_broken_relation_databag_when_set_certificate_then_error_is_logged(
        self, caplog: pytest.LogCaptureFixture, databag_value: str, error_msg: str
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": databag_value},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        self.ctx.run(self.ctx.on.relation_changed(relation), state_in)

        logs = [(record.levelname, record.module, record.message) for record in caplog.records]
        assert (
            "ERROR",
            "_certificate_transfer",
            error_msg,
        ) in logs

    def test_given_invalid_relation_data_when_is_ready_then_false_is_returned(self):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": "some string"},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        self.ctx.run(
            self.ctx.on.action("is-ready", params={"relation-id": str(relation.id)}),
            state_in,
        )
        assert self.ctx.action_results
        assert not self.ctx.action_results["is-ready"]

    def test_given_valid_relation_data_when_is_ready_then_true_is_returned(self):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        self.ctx.run(
            self.ctx.on.action("is-ready", params={"relation-id": str(relation.id)}),
            state_in,
        )
        assert self.ctx.action_results
        assert self.ctx.action_results["is-ready"]

    def test_given_certificates_in_relation_data_when_get_all_certificates_by_relation_then_sorted_list_returned(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert_z", "cert_a", "cert_m"])},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.update_status(), state_in) as manager:
            charm = manager.charm
            result = charm.certificate_transfer.get_all_certificates_by_relation()

        assert relation.id in result
        assert result[relation.id] == ["cert_a", "cert_m", "cert_z"]

    def test_given_multiple_relations_when_get_all_certificates_by_relation_then_all_relations_returned(
        self,
    ):
        relation_1 = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert_b", "cert_a"])},
        )
        relation_2 = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert_y", "cert_x"])},
        )
        state_in = scenario.State(leader=True, relations=[relation_1, relation_2])

        with self.ctx(self.ctx.on.update_status(), state_in) as manager:
            charm = manager.charm
            result = charm.certificate_transfer.get_all_certificates_by_relation()

        assert relation_1.id in result
        assert relation_2.id in result
        assert result[relation_1.id] == ["cert_a", "cert_b"]
        assert result[relation_2.id] == ["cert_x", "cert_y"]

    def test_given_no_relation_when_get_all_certificates_by_relation_then_empty_dict_returned(
        self,
    ):
        state_in = scenario.State()

        with self.ctx(self.ctx.on.update_status(), state_in) as manager:
            charm = manager.charm
            result = charm.certificate_transfer.get_all_certificates_by_relation()

        assert result == {}

    def _run_relation_changed(
        self, relation: scenario.Relation, state_in: scenario.State
    ) -> tuple[scenario.State, list[CertificatesAvailableEvent]]:
        """Run relation-changed, returning the output state and the newly emitted events."""
        already_emitted = len(self.ctx.emitted_events)
        state_out = self.ctx.run(self.ctx.on.relation_changed(relation), state_in)
        events = [
            e
            for e in self.ctx.emitted_events[already_emitted:]
            if isinstance(e, CertificatesAvailableEvent)
        ]
        return state_out, events

    def test_given_unchanged_certificates_when_relation_changed_again_then_event_not_emitted(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1", "cert2"])},
        )
        state_out, events = self._run_relation_changed(
            relation, scenario.State(relations=[relation])
        )
        assert len(events) == 1

        _, events = self._run_relation_changed(relation, state_out)

        assert events == []

    def test_given_reordered_certificates_when_relation_changed_then_event_not_emitted(self):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1", "cert2", "cert3"])},
        )
        state_out, events = self._run_relation_changed(
            relation, scenario.State(relations=[relation])
        )
        assert len(events) == 1

        reordered = dataclasses.replace(
            relation, remote_app_data={"certificates": json.dumps(["cert3", "cert1", "cert2"])}
        )
        _, events = self._run_relation_changed(
            reordered, dataclasses.replace(state_out, relations=[reordered])
        )

        assert events == []

    def test_given_changed_certificates_when_relation_changed_then_event_emitted(self):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        state_out, events = self._run_relation_changed(
            relation, scenario.State(relations=[relation])
        )
        assert len(events) == 1

        updated = dataclasses.replace(
            relation, remote_app_data={"certificates": json.dumps(["cert1", "cert2"])}
        )
        _, events = self._run_relation_changed(
            updated, dataclasses.replace(state_out, relations=[updated])
        )

        assert len(events) == 1
        assert events[0].certificates == {"cert1", "cert2"}
        assert events[0].relation_id == relation.id

    def test_given_certificates_removed_then_restored_when_relation_changed_then_event_emitted(
        self,
    ):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        state_out, _ = self._run_relation_changed(relation, scenario.State(relations=[relation]))
        emptied = dataclasses.replace(relation, remote_app_data={"certificates": json.dumps([])})
        state_out, events = self._run_relation_changed(
            emptied, dataclasses.replace(state_out, relations=[emptied])
        )
        assert len(events) == 1
        assert events[0].certificates == set()

        _, events = self._run_relation_changed(
            relation, dataclasses.replace(state_out, relations=[relation])
        )

        assert len(events) == 1
        assert events[0].certificates == {"cert1"}

    def test_given_multiple_relations_when_each_relation_changed_then_hashes_tracked_per_relation(
        self,
    ):
        relation_1 = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        relation_2 = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        state_out, events = self._run_relation_changed(
            relation_1, scenario.State(relations=[relation_1, relation_2])
        )
        assert len(events) == 1

        _, events = self._run_relation_changed(relation_2, state_out)

        assert len(events) == 1
        assert events[0].relation_id == relation_2.id

    def test_given_relation_broken_then_stored_hash_is_removed(self):
        relation = scenario.Relation(
            endpoint="certificate_transfer",
            interface="certificate_transfer",
            local_app_data={"version": "1"},
            remote_app_data={"certificates": json.dumps(["cert1"])},
        )
        state_out, _ = self._run_relation_changed(relation, scenario.State(relations=[relation]))
        stored = state_out.get_stored_state("_stored", owner_path=STORED_STATE_OWNER)
        assert f"certificate_transfer:{relation.id}" in stored.content["certificate_hashes"]

        state_out = self.ctx.run(self.ctx.on.relation_broken(relation), state_out)

        stored = state_out.get_stored_state("_stored", owner_path=STORED_STATE_OWNER)
        assert f"certificate_transfer:{relation.id}" not in stored.content["certificate_hashes"]
