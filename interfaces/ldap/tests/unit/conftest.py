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

"""Fixtures for unit tests"""

from typing import Any

import pytest
import yaml
from ops import CharmBase, EventBase
from ops.testing import Context, State

from charmlibs.interfaces.ldap import LdapRequirer

METADATA = """
name: requirer-tester
requires:
  ldap:
    interface: ldap
"""


class LdapRequirerCharm(CharmBase):
    """Test charm that wraps LdapRequirer and records emitted events."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.events: list[EventBase] = []
        self.ldap_requirer = LdapRequirer(self)
        self.framework.observe(
            self.ldap_requirer.on.ldap_ready,
            self._record_event,
        )
        self.framework.observe(
            self.ldap_requirer.on.ldap_unavailable,
            self._record_event,
        )

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture
def context() -> Context:
    """ops.testing Context for the test LdapRequirerCharm."""
    return Context(LdapRequirerCharm, meta=yaml.safe_load(METADATA), juju_version='3.2.1')


@pytest.fixture
def provider_data() -> dict[str, str]:
    """Minimal LDAP provider relation data."""
    return {
        'urls': '["ldap://path.to.glauth:3893"]',
        'ldaps_urls': '["ldaps://path.to.glauth:3894"]',
        'base_dn': 'dc=glauth,dc=com',
        'starttls': 'true',
        'bind_dn': 'cn=serviceuser,ou=svcaccts,dc=glauth,dc=com',
        'bind_password_secret': '',
        'auth_method': 'simple',
    }


@pytest.fixture
def requirer_data() -> dict[str, str]:
    """Expected LDAP requirer relation data."""
    return {
        'user': 'requirer-tester',
        'group': 'test',
    }


def create_state(
    leader: bool = True,
    secrets: list | None = None,
    relations: list | None = None,
    containers: list | None = None,
    config: dict | None = None,
) -> State:
    """Create a State with sensible defaults."""
    return State(
        leader=leader,
        secrets=secrets or [],
        containers=containers or [],
        relations=relations or [],
        config=config or {},
    )
