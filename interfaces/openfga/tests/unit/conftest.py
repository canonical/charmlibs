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

"""Fixtures for openfga unit tests."""

import typing

import ops
import ops.testing
import pytest

from charmlibs.interfaces.openfga import (
    OpenFGAProvider,
    OpenFGARequires,
    OpenFGAStoreCreateEvent,
    OpenFGAStoreRemovedEvent,
    OpenFGAStoreRequestEvent,
)


class RequirerCharm(ops.CharmBase):
    """Test charm for OpenFGARequires."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.openfga = OpenFGARequires(self, 'my-store-name')
        self.events_emitted: list[tuple[str, typing.Any]] = []
        self.framework.observe(self.openfga.on.openfga_store_created, self._on_store_created)
        self.framework.observe(self.openfga.on.openfga_store_removed, self._on_store_removed)

    def _on_store_created(self, event: OpenFGAStoreCreateEvent) -> None:
        self.events_emitted.append(('created', event.store_id))

    def _on_store_removed(self, event: OpenFGAStoreRemovedEvent) -> None:
        self.events_emitted.append(('removed', event))


class ProviderCharm(ops.CharmBase):
    """Test charm for OpenFGAProvider."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.openfga = OpenFGAProvider(self)
        self.events_emitted: list[tuple[str, typing.Any, int]] = []
        self.framework.observe(self.openfga.on.openfga_store_requested, self._on_store_requested)

    def _on_store_requested(self, event: OpenFGAStoreRequestEvent) -> None:
        assert event.relation.id is not None
        self.events_emitted.append(('requested', event.store_name, event.relation.id))


@pytest.fixture
def requirer_ctx() -> ops.testing.Context[RequirerCharm]:
    """Fixture for RequirerCharm Context."""
    return ops.testing.Context(
        RequirerCharm,
        meta={'name': 'requirer', 'requires': {'openfga': {'interface': 'openfga'}}},
    )


@pytest.fixture
def provider_ctx() -> ops.testing.Context[ProviderCharm]:
    """Fixture for ProviderCharm Context."""
    return ops.testing.Context(
        ProviderCharm,
        meta={'name': 'provider', 'provides': {'openfga': {'interface': 'openfga'}}},
    )
