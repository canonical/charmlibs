# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any, cast

import pytest
import scenario
from ops.charm import CharmBase

from charmlibs.interfaces.k8s_backup_target import (
    K8sBackupTargetProvider,
    K8sBackupTargetRequirer,
    K8sBackupTargetSpec,
)


def _make_backup_targets_databag(
    app: str = "test-app",
    relation_name: str = "backup",
    model: str = "test-model",
    spec: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Helper to build a remote_app_data dict in the nested backup_targets format."""
    entry: dict[str, Any] = {
        "app": app,
        "relation_name": relation_name,
        "model": model,
        "spec": spec or {},
    }
    return {"backup_targets": json.dumps([entry], sort_keys=True)}


class DummyProviderCharm(CharmBase):
    """Dummy charm for testing K8sBackupTargetProvider."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.backup = K8sBackupTargetProvider(
            self,
            relation_name="backup",
            spec=K8sBackupTargetSpec(
                include_namespaces=["my-namespace"],
                include_resources=["persistentvolumeclaims", "services"],
                ttl="24h",
            ),
            refresh_event=[self.on.config_changed],
        )


class DummyRequirerCharm(CharmBase):
    """Dummy charm for testing K8sBackupTargetRequirer."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.backup_requirer = K8sBackupTargetRequirer(self, relation_name="k8s-backup-target")


class TestK8sBackupTargetProvider:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = scenario.Context(
            charm_type=DummyProviderCharm,
            meta={
                "name": "backup-provider",
                "provides": {"backup": {"interface": "k8s_backup_target"}},
            },
        )

    def test_given_relation_when_relation_created_then_data_is_sent(self):
        relation = scenario.Relation(
            endpoint="backup",
            interface="k8s_backup_target",
        )
        state_in = scenario.State(leader=True, relations=[relation])

        state_out = self.ctx.run(self.ctx.on.relation_created(relation), state_in)

        relation_out = state_out.get_relation(relation.id)
        local_app_data = relation_out.local_app_data
        assert "backup_targets" in local_app_data
        parsed: object = json.loads(local_app_data["backup_targets"])
        assert isinstance(parsed, list)
        targets = cast("list[dict[str, Any]]", parsed)
        assert len(targets) == 1
        entry = targets[0]
        assert entry["app"] == "backup-provider"
        assert entry["relation_name"] == "backup"
        assert entry["spec"]["include_namespaces"] == ["my-namespace"]
        assert entry["spec"]["include_resources"] == ["persistentvolumeclaims", "services"]
        assert entry["spec"]["ttl"] == "24h"

    def test_given_not_leader_when_relation_created_then_no_data_sent(
        self, caplog: pytest.LogCaptureFixture
    ):
        relation = scenario.Relation(
            endpoint="backup",
            interface="k8s_backup_target",
        )
        state_in = scenario.State(leader=False, relations=[relation])

        state_out = self.ctx.run(self.ctx.on.relation_created(relation), state_in)

        relation_out = state_out.get_relation(relation.id)
        assert relation_out.local_app_data == {}
        assert "not a leader" in caplog.text.lower()

    def test_given_relation_when_config_changed_then_data_is_refreshed(self):
        relation = scenario.Relation(
            endpoint="backup",
            interface="k8s_backup_target",
        )
        state_in = scenario.State(leader=True, relations=[relation])

        state_out = self.ctx.run(self.ctx.on.config_changed(), state_in)

        relation_out = state_out.get_relation(relation.id)
        assert "backup_targets" in relation_out.local_app_data

    def test_given_no_relation_when_leader_elected_then_warning_logged(
        self, caplog: pytest.LogCaptureFixture
    ):
        state_in = scenario.State(leader=True, relations=[])

        self.ctx.run(self.ctx.on.leader_elected(), state_in)

        assert "no relation" in caplog.text.lower()


class TestK8sBackupTargetRequirer:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = scenario.Context(
            charm_type=DummyRequirerCharm,
            meta={
                "name": "backup-requirer",
                "requires": {"k8s-backup-target": {"interface": "k8s_backup_target"}},
            },
        )

    def test_given_relation_with_data_when_get_all_specs_then_specs_returned(self):
        spec_data = {
            "include_namespaces": ["test-namespace"],
            "include_resources": ["deployments"],
            "ttl": "48h",
        }
        relation = scenario.Relation(
            endpoint="k8s-backup-target",
            interface="k8s_backup_target",
            remote_app_data=_make_backup_targets_databag(spec=spec_data),
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            specs = charm.backup_requirer.get_all_backup_specs()

            assert len(specs) == 1
            assert specs[0].include_namespaces == ["test-namespace"]
            assert specs[0].include_resources == ["deployments"]
            assert specs[0].ttl == "48h"

    def test_given_relation_with_data_when_get_backup_spec_then_spec_returned(self):
        spec_data = {
            "include_namespaces": ["my-ns"],
            "include_resources": ["services"],
        }
        relation = scenario.Relation(
            endpoint="k8s-backup-target",
            interface="k8s_backup_target",
            remote_app_data=_make_backup_targets_databag(
                app="my-app", relation_name="backup", model="my-model", spec=spec_data
            ),
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            spec = charm.backup_requirer.get_backup_spec(
                app_name="my-app", endpoint="backup", model="my-model"
            )

            assert spec is not None
            assert spec.include_namespaces == ["my-ns"]
            assert spec.include_resources == ["services"]

    def test_given_no_matching_relation_when_get_backup_spec_then_none_returned(
        self, caplog: pytest.LogCaptureFixture
    ):
        spec_data = {"include_namespaces": ["ns1"]}
        relation = scenario.Relation(
            endpoint="k8s-backup-target",
            interface="k8s_backup_target",
            remote_app_data=_make_backup_targets_databag(
                app="other-app", relation_name="backup", model="other-model", spec=spec_data
            ),
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            spec = charm.backup_requirer.get_backup_spec(
                app_name="my-app", endpoint="backup", model="my-model"
            )

            assert spec is None
            assert "no backup spec found" in caplog.text.lower()

    def test_given_valid_data_when_is_ready_then_true(self):
        relation = scenario.Relation(
            endpoint="k8s-backup-target",
            interface="k8s_backup_target",
            remote_app_data=_make_backup_targets_databag(spec={"include_namespaces": ["ns1"]}),
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            assert charm.backup_requirer.is_ready is True

    def test_given_no_relation_when_is_ready_then_false(self):
        state_in = scenario.State(leader=True, relations=[])

        with self.ctx(self.ctx.on.update_status(), state_in) as mgr:
            charm = mgr.charm
            assert charm.backup_requirer.is_ready is False

    def test_given_empty_databag_when_is_ready_then_false(self):
        relation = scenario.Relation(
            endpoint="k8s-backup-target",
            interface="k8s_backup_target",
            remote_app_data={},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            assert charm.backup_requirer.is_ready is False

    def test_given_garbage_data_when_is_ready_then_false(self):
        relation = scenario.Relation(
            endpoint="k8s-backup-target",
            interface="k8s_backup_target",
            remote_app_data={"backup_targets": "not-valid-json{{{"},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            assert charm.backup_requirer.is_ready is False

    def test_given_garbage_data_when_get_all_specs_then_empty_list(self):
        relation = scenario.Relation(
            endpoint="k8s-backup-target",
            interface="k8s_backup_target",
            remote_app_data={"backup_targets": "not-valid-json{{{"},
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            specs = charm.backup_requirer.get_all_backup_specs()
            assert specs == []


class TestK8sBackupTargetSpec:
    def test_valid_ttl_formats(self):
        valid_ttls = ["24h", "1h30m", "10m10s", "30s", "1h", "1h1m1s"]
        for ttl in valid_ttls:
            spec = K8sBackupTargetSpec(ttl=ttl)
            assert spec.ttl == ttl

    def test_spec_with_all_fields(self):
        spec = K8sBackupTargetSpec(
            include_namespaces=["ns1", "ns2"],
            include_resources=["deployments", "services"],
            exclude_namespaces=["kube-system"],
            exclude_resources=["secrets"],
            label_selector={"app": "myapp"},
            ttl="72h",
            include_cluster_resources=True,
        )
        assert spec.include_namespaces == ["ns1", "ns2"]
        assert spec.include_resources == ["deployments", "services"]
        assert spec.exclude_namespaces == ["kube-system"]
        assert spec.exclude_resources == ["secrets"]
        assert spec.label_selector == {"app": "myapp"}
        assert spec.ttl == "72h"
        assert spec.include_cluster_resources is True

    def test_spec_with_defaults(self):
        spec = K8sBackupTargetSpec()
        assert spec.include_namespaces is None
        assert spec.include_resources is None
        assert spec.exclude_namespaces is None
        assert spec.exclude_resources is None
        assert spec.label_selector is None
        assert spec.ttl is None
        assert spec.include_cluster_resources is None
