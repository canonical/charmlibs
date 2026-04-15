# Copyright 2026 Canonical
# See LICENSE file for licensing details.

from interface_tester import Tester
from scenario import Relation, State


def test_nothing_happens_if_remote_empty():
    # GIVEN that the remote end has not published any tables
    t = Tester(
        State(
            leader=True,
            relations=[
                Relation(
                    endpoint="valkey-client",  # the name doesn't matter
                    interface="valkey_client",
                )
            ],
        )
    )
    # WHEN the database charm receives a relation-joined event
    state_out = t.run("valkey-client-relation-joined")
    # THEN no data is published to the (local) databags
    t.assert_relation_data_empty()


def test_add_provider_content():
    # GIVEN that the remote end has requested tables in the right format
    t = Tester(
        State(
            leader=True,
            relations=[
                Relation(
                    endpoint="valkey-client",  # the name doesn't matter
                    interface="valkey_client",
                    remote_app_data={
                        "prefix": "my_keys:*",
                        "requested-secrets": ["username", "password", "tls", "tls-ca"],
                    },
                )
            ],
        )
    )
    # WHEN the database charm receives a relation-changed event
    state_out = t.run("valkey-client-relation-changed")
    # THEN the schema is satisfied (the database charm published all required fields)
    t.assert_schema_valid()
