# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Regression tests for dynamic cluster_id becoming available after the etcd
relation has already been created.

These reproduce the race condition where:
  1. The etcd relation is created before the charm has a cluster_id, so the
     etcd backend (and therefore the requirer that publishes the request) is
     never set up for that relation-created event.
  2. The cluster_id becomes available on a later event, but without a fix the
     request is never (re)published because the relation-created event has
     already fired and won't fire again.
"""

from typing import Any, ClassVar
from unittest.mock import MagicMock

import ops
import pytest
from ops.testing import Context, PeerRelation, Relation, State
from tests.unit.conftest import meta


class DynamicClusterIdCharm(ops.CharmBase):
    """Charm whose cluster_id is provided dynamically, mimicking real usage.

    Tests toggle ``DynamicClusterIdCharm.cluster_id`` to simulate the cluster_id
    becoming available only on a later event, after the etcd relation already
    exists.
    """

    cluster_id: ClassVar[str | None] = None

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)

        from charmlibs.rollingops import RollingOpsManager

        self.restart_manager = RollingOpsManager(
            charm=self,
            peer_relation_name='restart',
            etcd_relation_name='etcd',
            cluster_id=DynamicClusterIdCharm.cluster_id,
            callback_targets={},
        )


@pytest.fixture
def dynamic_ctx() -> Context[DynamicClusterIdCharm]:
    return Context(DynamicClusterIdCharm, meta=meta)


@pytest.fixture(autouse=True)
def _reset_cluster_id() -> Any:  # pyright: ignore[reportUnusedFunction] (autouse fixture)
    DynamicClusterIdCharm.cluster_id = None
    yield
    DynamicClusterIdCharm.cluster_id = None


def test_request_not_published_while_cluster_id_is_missing(
    certificates_manager_patches: dict[str, MagicMock],
    dynamic_ctx: Context[DynamicClusterIdCharm],
):
    """No etcd request is written while cluster_id has not been provided yet."""
    peer = PeerRelation(endpoint='restart')
    etcd_relation = Relation(endpoint='etcd', interface='etcd_client')
    state_in = State(leader=True, relations={peer, etcd_relation})

    DynamicClusterIdCharm.cluster_id = None
    state_out = dynamic_ctx.run(dynamic_ctx.on.relation_created(etcd_relation), state_in)

    etcd_out = next(r for r in state_out.relations if r.endpoint == 'etcd')
    assert 'requests' not in etcd_out.local_app_data


def test_request_published_once_cluster_id_becomes_available_for_existing_relation(
    certificates_manager_patches: dict[str, MagicMock],
    dynamic_ctx: Context[DynamicClusterIdCharm],
):
    """Once cluster_id becomes available, the request is published for the
    already-existing relation, without needing the relation to be recreated.
    """
    peer = PeerRelation(endpoint='restart')
    etcd_relation = Relation(endpoint='etcd', interface='etcd_client')
    state_in = State(leader=True, relations={peer, etcd_relation})

    # Step 1: relation is created while cluster_id is not yet available.
    DynamicClusterIdCharm.cluster_id = None
    state_mid = dynamic_ctx.run(dynamic_ctx.on.relation_created(etcd_relation), state_in)

    etcd_mid = next(r for r in state_mid.relations if r.endpoint == 'etcd')
    assert 'requests' not in etcd_mid.local_app_data

    # Step 2: cluster_id becomes available on a later, unrelated event. The
    # relation is NOT recreated.
    DynamicClusterIdCharm.cluster_id = 'cluster-12345'
    state_out = dynamic_ctx.run(dynamic_ctx.on.update_status(), state_mid)

    etcd_out = next(r for r in state_out.relations if r.endpoint == 'etcd')
    assert 'requests' in etcd_out.local_app_data
    assert 'cluster-12345' in etcd_out.local_app_data['requests']


def test_request_is_published_only_once(
    certificates_manager_patches: dict[str, MagicMock],
    dynamic_ctx: Context[DynamicClusterIdCharm],
):
    """Once a request has been published, later events do not rewrite it."""
    peer = PeerRelation(endpoint='restart')
    etcd_relation = Relation(endpoint='etcd', interface='etcd_client')
    state_in = State(leader=True, relations={peer, etcd_relation})

    DynamicClusterIdCharm.cluster_id = 'cluster-12345'
    state_mid = dynamic_ctx.run(dynamic_ctx.on.update_status(), state_in)

    etcd_mid = next(r for r in state_mid.relations if r.endpoint == 'etcd')
    first_requests = etcd_mid.local_app_data['requests']

    state_out = dynamic_ctx.run(dynamic_ctx.on.update_status(), state_mid)
    etcd_out = next(r for r in state_out.relations if r.endpoint == 'etcd')

    # The request_id (derived from a random salt) must stay stable across
    # republish attempts: it must not be regenerated into a brand new request.
    assert etcd_out.local_app_data['requests'] == first_requests
