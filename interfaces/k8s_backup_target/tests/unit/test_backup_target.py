# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any

import pytest
import scenario
from ops.charm import CharmBase

from charmlibs.interfaces.k8s_backup_target import (
    BackupTargetProvider,
    BackupTargetRequirer,
    BackupTargetSpec,
)


class DummyProviderCharm(CharmBase):
    """Dummy charm for testing BackupTargetProvider."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.backup = BackupTargetProvider(
            self,
            relation_name="backup",
            spec=BackupTargetSpec(
                include_namespaces=["my-namespace"],
                include_resources=["persistentvolumeclaims", "services"],
                ttl="24h",
            ),
            refresh_event=[self.on.config_changed],
        )


class DummyRequirerCharm(CharmBase):
    """Dummy charm for testing BackupTargetRequirer."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.backup_requirer = BackupTargetRequirer(self, relation_name="k8s-backup-target")


class TestBackupTargetProvider:
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
        assert local_app_data["app"] == "backup-provider"
        assert local_app_data["relation_name"] == "backup"
        assert "spec" in local_app_data
        spec_data = json.loads(local_app_data["spec"])
        assert spec_data["include_namespaces"] == ["my-namespace"]
        assert spec_data["include_resources"] == ["persistentvolumeclaims", "services"]
        assert spec_data["ttl"] == "24h"

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
        assert "spec" in relation_out.local_app_data

    def test_given_no_relation_when_leader_elected_then_warning_logged(
        self, caplog: pytest.LogCaptureFixture
    ):
        state_in = scenario.State(leader=True, relations=[])

        self.ctx.run(self.ctx.on.leader_elected(), state_in)

        assert "no relation" in caplog.text.lower()


class TestBackupTargetRequirer:
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
            remote_app_data={
                "app": "test-app",
                "relation_name": "backup",
                "model": "test-model",
                "spec": json.dumps(spec_data),
            },
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
            remote_app_data={
                "app": "my-app",
                "relation_name": "backup",
                "model": "my-model",
                "spec": json.dumps(spec_data),
            },
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
            remote_app_data={
                "app": "other-app",
                "relation_name": "backup",
                "model": "other-model",
                "spec": json.dumps(spec_data),
            },
        )
        state_in = scenario.State(leader=True, relations=[relation])

        with self.ctx(self.ctx.on.relation_changed(relation), state_in) as mgr:
            charm = mgr.charm
            spec = charm.backup_requirer.get_backup_spec(
                app_name="my-app", endpoint="backup", model="my-model"
            )

            assert spec is None
            assert "no backup spec found" in caplog.text.lower()


class TestBackupTargetSpec:
    def test_valid_ttl_formats(self):
        valid_ttls = ["24h", "1h30m", "10m10s", "30s", "1h", "1h1m1s"]
        for ttl in valid_ttls:
            spec = BackupTargetSpec(ttl=ttl)
            assert spec.ttl == ttl

    def test_spec_with_all_fields(self):
        spec = BackupTargetSpec(
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
        spec = BackupTargetSpec()
        assert spec.include_namespaces is None
        assert spec.include_resources is None
        assert spec.exclude_namespaces is None
        assert spec.exclude_resources is None
        assert spec.label_selector is None
        assert spec.ttl is None
        assert spec.include_cluster_resources is None
