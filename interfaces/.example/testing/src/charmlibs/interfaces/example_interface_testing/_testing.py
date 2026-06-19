# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from ops import testing

# from charmlibs.interfaces import example_interface

_INTERFACE_NAME = 'example-interface'


def relation_for_requirer(
    endpoint: str,
    # *,  # Additional arguments must be keyword only.
    # response: bool = True,  # Request-response interfaces default to populating both sides.
) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME)


def relation_for_provider(
    endpoint: str,
    # *,  # Additional arguments must be keyword only.
    # response: bool = True,  # Request-response interfaces default to populating both sides.
) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME)
