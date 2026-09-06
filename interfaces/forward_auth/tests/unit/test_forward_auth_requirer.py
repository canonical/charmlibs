# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any

from ops.charm import CharmBase
from ops.testing import Context, Relation, State

from charmlibs.interfaces.forward_auth import (
    AuthConfigChangedEvent,
    AuthConfigRemovedEvent,
    ForwardAuthRequirer,
    ForwardAuthRequirerConfig,
)
from conftest import (
    FORWARD_AUTH_CONFIG,
    FORWARD_AUTH_REQUIRER_CONFIG,
    dict_to_relation_data,
)

METADATA = """
name: requirer-tester
requires:
  forward-auth:
    interface: forward_auth
    limit: 1
"""


class ForwardAuthRequirerCharm(CharmBase):
    """Test charm implementing the ForwardAuthRequirer."""

    test_config = FORWARD_AUTH_REQUIRER_CONFIG

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        forward_auth_config = (
            ForwardAuthRequirerConfig(**self.test_config) if self.test_config else None
        )
        self.forward_auth = ForwardAuthRequirer(self)
        self.forward_auth.update_requirer_relation_data(forward_auth_config)


class TestForwardAuthRequirerIntegration:
    """Unit tests for the ForwardAuthRequirer class."""

    def test_data_in_relation_bag(
        self,
        context: Context[ForwardAuthRequirerCharm],
        forward_auth_relation_requirer: Relation,
    ) -> None:
        """Verifies that config is correctly written to the relation databag."""
        state_in = context.run(
            context.on.relation_created(forward_auth_relation_requirer),
            State(relations=[forward_auth_relation_requirer], leader=True),
        )

        rel_out = state_in.get_relation(forward_auth_relation_requirer.id)
        assert rel_out.local_app_data == dict_to_relation_data(FORWARD_AUTH_REQUIRER_CONFIG)

    def test_get_provider_info_when_data_available(
        self,
        context: Context[ForwardAuthRequirerCharm],
        forward_auth_relation_requirer: Relation,
    ) -> None:
        """Verifies that provider info can be retrieved successfully from relation data."""
        with context(
            context.on.relation_changed(forward_auth_relation_requirer),
            State(relations=[forward_auth_relation_requirer], leader=True),
        ) as manager:
            manager.run()

            expected_provider_info = manager.charm.forward_auth.get_provider_info()
            assert expected_provider_info is not None
            assert (
                expected_provider_info.decisions_address
                == FORWARD_AUTH_CONFIG['decisions_address']
            )
            assert expected_provider_info.app_names == FORWARD_AUTH_CONFIG['app_names']
            assert expected_provider_info.headers == FORWARD_AUTH_CONFIG['headers']

    def test_forward_auth_config_changed_emitted_when_relation_changed(
        self,
        context: Context[ForwardAuthRequirerCharm],
        forward_auth_relation_requirer: Relation,
    ) -> None:
        """Verifies that AuthConfigChangedEvent is emitted when the relation changes."""
        context.run(
            context.on.relation_changed(forward_auth_relation_requirer),
            State(relations=[forward_auth_relation_requirer], leader=True),
        )

        assert any(isinstance(e, AuthConfigChangedEvent) for e in context.emitted_events)

    def test_forward_auth_removed_emitted_when_relation_removed(
        self,
        context: Context[ForwardAuthRequirerCharm],
        forward_auth_relation_requirer: Relation,
    ) -> None:
        """Verifies that AuthConfigRemovedEvent is emitted when the relation is broken."""
        state_in = State(relations=[forward_auth_relation_requirer], leader=True)
        context.run(context.on.relation_broken(forward_auth_relation_requirer), state_in)
        assert any(isinstance(e, AuthConfigRemovedEvent) for e in context.emitted_events)
