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

import json
from typing import Any

import pytest
import yaml
from ops import CharmBase
from ops.testing import Context, Relation, State

from charmlibs.interfaces.ldap import (
    LdapProvider,
    LdapProviderBaseData,
    LdapProviderData,
)

PROVIDER_METADATA = """
name: provider-tester
provides:
  ldap:
    interface: ldap
"""


class LdapProviderCharm(CharmBase):
    """Test charm that wraps LdapProvider."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.ldap_provider = LdapProvider(self)


@pytest.fixture
def provider_context() -> Context:
    """ops.testing Context for the test LdapProviderCharm."""
    return Context(LdapProviderCharm, meta=yaml.safe_load(PROVIDER_METADATA), juju_version='3.2.1')


@pytest.mark.parametrize(
    'ldaps_urls, expected_enabled',
    [
        (['ldaps://path.to.glauth:3894'], True),
        ([], False),
    ],
)
def test_update_relations_app_data_ldaps_urls_and_property(
    provider_context: Context, ldaps_urls: list[str], expected_enabled: bool
) -> None:
    relation = Relation('ldap')
    state = State(leader=True, relations=[relation])

    with provider_context(provider_context.on.update_status(), state) as mgr:
        data = LdapProviderData(
            urls=['ldap://path.to.glauth:3893'],
            ldaps_urls=ldaps_urls,
            base_dn='dc=glauth,dc=com',
            bind_dn='cn=serviceuser,ou=svcaccts,dc=glauth,dc=com',
            bind_password='password',
            auth_method='simple',
            starttls=True,
        )
        assert data.ldaps_enabled is expected_enabled

        mgr.charm.ldap_provider.update_relations_app_data(data, relation_id=relation.id)
        state_out = mgr.run()

    app_data = state_out.get_relation(relation.id).local_app_data
    assert app_data['ldaps_urls'] == json.dumps(ldaps_urls)
    assert 'ldaps_enabled' not in app_data


def test_base_data_ldaps_enabled_property() -> None:
    data_with_ldaps = LdapProviderBaseData(
        urls=['ldap://path.to.glauth:3893'],
        ldaps_urls=['ldaps://path.to.glauth:3894'],
        base_dn='dc=glauth,dc=com',
        starttls=True,
    )
    assert data_with_ldaps.ldaps_enabled is True

    data_without_ldaps = LdapProviderBaseData(
        urls=['ldap://path.to.glauth:3893'],
        ldaps_urls=[],
        base_dn='dc=glauth,dc=com',
        starttls=True,
    )
    assert data_without_ldaps.ldaps_enabled is False
