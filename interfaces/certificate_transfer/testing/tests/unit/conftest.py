# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures. Also the idiomatic shape of a charm repository's own conftest."""

from __future__ import annotations

import typing

import ops.testing
import pytest

import provider_charm
import requirer_charm
from charmlibs.interfaces import certificate_transfer_testing

if typing.TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture()
def mocked() -> Iterator[None]:
    """Open the library's mocking scope for the whole test, arrangement and act alike."""
    with certificate_transfer_testing.mocked():
        yield


@pytest.fixture()
def requirer_ctx() -> ops.testing.Context[requirer_charm.RequirerCharm]:
    """A context for the requirer charm, which is tested with a RemoteProvider."""
    return ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)


@pytest.fixture()
def provider_ctx() -> ops.testing.Context[provider_charm.ProviderCharm]:
    """A context for the provider charm, which is tested with a RemoteRequirer."""
    return ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
