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
#
# Learn more about testing at: https://juju.is/docs/sdk/testing


from charmlibs.advanced_rollingops import (
    RollingOpsKeys,
)


def test_rollingopskeys_paths() -> None:
    keys = RollingOpsKeys.for_owner('cluster-a', 'unit-1')

    assert keys.cluster_prefix == '/rollingops/cluster-a/'
    assert keys._owner_prefix == '/rollingops/cluster-a/unit-1'
    assert keys.lock_key == '/rollingops/cluster-a/granted-unit'
    assert keys.pending == '/rollingops/cluster-a/unit-1/pending/'
    assert keys.inprogress == '/rollingops/cluster-a/unit-1/inprogress/'
    assert keys.completed == '/rollingops/cluster-a/unit-1/completed/'


def test_rollingopskeys_lock_key_is_shared_within_cluster() -> None:
    k1 = RollingOpsKeys.for_owner('cluster-a', 'unit-1')
    k2 = RollingOpsKeys.for_owner('cluster-a', 'unit-2')

    assert k1.lock_key == k2.lock_key
    assert k1.pending != k2.pending
    assert k1.inprogress != k2.inprogress
    assert k1.completed != k2.completed
