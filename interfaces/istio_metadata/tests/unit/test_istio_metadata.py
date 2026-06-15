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

"""Tests for the istio_metadata lib requirer and provider classes.

Ported from `tests/unit/test_istio_metadata_lib.py` in the istio-k8s-operator
repository.
"""

from __future__ import annotations

from typing import ClassVar

import ops
import pytest
from ops import CharmBase
from ops.testing import Context, Relation, State

from charmlibs.interfaces.istio_metadata import (
    IstioMetadataAppData,
    IstioMetadataProvider,
    IstioMetadataRequirer,
)

RELATION_NAME = 'app-data-relation'
INTERFACE_NAME = 'app-data-interface'

# Note: if this is changed, the IstioMetadataAppData concrete classes below need to change
# their constructors to match.
SAMPLE_APP_DATA = IstioMetadataAppData(root_namespace='root-namespace')
SAMPLE_APP_DATA_2 = IstioMetadataAppData(root_namespace='root-namespace-2')


class IstioMetadataProviderCharm(CharmBase):
    META: ClassVar = {
        'name': 'provider',
        'provides': {RELATION_NAME: {'interface': INTERFACE_NAME}},
    }

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.relation_provider = IstioMetadataProvider(
            charm=self,
            relation_mapping=self.model.relations,
            app=self.app,
            relation_name=RELATION_NAME,
        )


@pytest.fixture
def istio_metadata_provider_context() -> Context[IstioMetadataProviderCharm]:
    return Context(charm_type=IstioMetadataProviderCharm, meta=IstioMetadataProviderCharm.META)


class IstioMetadataRequirerCharm(CharmBase):
    META: ClassVar = {
        'name': 'requirer',
        'requires': {RELATION_NAME: {'interface': INTERFACE_NAME}},
    }

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.relation_requirer = IstioMetadataRequirer(
            self.model.relations, relation_name=RELATION_NAME
        )


@pytest.fixture
def istio_metadata_requirer_context() -> Context[IstioMetadataRequirerCharm]:
    return Context(charm_type=IstioMetadataRequirerCharm, meta=IstioMetadataRequirerCharm.META)


@pytest.mark.parametrize('data', [SAMPLE_APP_DATA, SAMPLE_APP_DATA_2])
def test_istio_metadata_provider_sends_data_correctly(
    data: IstioMetadataAppData,
    istio_metadata_provider_context: Context[IstioMetadataProviderCharm],
):
    """Tests that a charm using IstioMetadataProvider sends the correct data during publish."""
    # Arrange
    istio_metadata_relation = Relation(RELATION_NAME, INTERFACE_NAME, local_app_data={})
    relations = [istio_metadata_relation]
    state = State(relations=relations, leader=True)

    # Act
    with istio_metadata_provider_context(
        # construct a charm using an event that won't trigger anything here
        istio_metadata_provider_context.on.update_status(),
        state=state,
    ) as manager:
        # Manually do a .publish() to simulate the publish, but also do .run() to generate
        # the state_out that we need to inspect the relation data.
        manager.charm.relation_provider.publish(**data.model_dump())
        state_out = manager.run()

    # Assert
    actual = IstioMetadataAppData.model_validate(
        dict(state_out.get_relation(istio_metadata_relation.id).local_app_data)
    )
    assert actual == data


@pytest.mark.parametrize(
    ('relations', 'expected_data'),
    [
        # no relations
        ([], None),
        # one empty relation
        (
            [Relation(RELATION_NAME, INTERFACE_NAME, remote_app_data={})],
            None,
        ),
        # one populated relation
        (
            [
                Relation(
                    RELATION_NAME,
                    INTERFACE_NAME,
                    remote_app_data=SAMPLE_APP_DATA.model_dump(mode='json'),
                )
            ],
            SAMPLE_APP_DATA,
        ),
    ],
)
def test_istio_metadata_requirer_get_data(
    relations: list[Relation],
    expected_data: IstioMetadataAppData | None,
    istio_metadata_requirer_context: Context[IstioMetadataRequirerCharm],
):
    """Tests that IstioMetadataRequirer.get_data() returns correctly."""
    state = State(relations=relations, leader=False)

    with istio_metadata_requirer_context(
        istio_metadata_requirer_context.on.update_status(), state=state
    ) as manager:
        charm = manager.charm
        data = charm.relation_requirer.get_data()
        assert _are_app_data_equal(data, expected_data)


def _are_app_data_equal(
    data1: IstioMetadataAppData | None, data2: IstioMetadataAppData | None
) -> bool:
    """Compare two IstioMetadataAppData objects, tolerating when one or both is None."""
    if data1 is None and data2 is None:
        return True
    if data1 is None or data2 is None:
        return False
    return data1.model_dump() == data2.model_dump()
