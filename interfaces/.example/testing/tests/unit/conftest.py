# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures shared by the testing package's own tests."""

from __future__ import annotations

import typing

import ops.testing
import pytest

import provider_charm
import requirer_charm
from charmlibs.interfaces import example_interface_testing as example_interface_testing

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

_Ctx: typing.TypeAlias = 'ops.testing.Context[ops.CharmBase]'


@pytest.fixture()
def mocked() -> Iterator[None]:
    """The library's mocking scope, which every state-producing call needs."""
    with example_interface_testing.mocked():
        yield


@pytest.fixture()
def requirer_ctx() -> _Ctx:
    """A context for the requirer charm, which is tested with a RemoteProvider."""
    return ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)


@pytest.fixture()
def provider_ctx() -> _Ctx:
    """A context for the provider charm, which is tested with a RemoteRequirer."""
    return ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
