# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures. Also the idiomatic shape of a charm repository's own conftest."""

from __future__ import annotations

import typing

import ops.testing
import pytest

import provider_charm
import requirer_charm
from charmlibs.interfaces import tls_certificates_testing

if typing.TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture()
def mocked() -> Iterator[None]:
    """Open the library's mocking scope for the whole test, arrangement and act alike."""
    with tls_certificates_testing.mocked():
        yield


@pytest.fixture()
def requirer_ctx() -> ops.testing.Context[requirer_charm.RequirerCharm]:
    return ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)


@pytest.fixture()
def provider_ctx() -> ops.testing.Context[provider_charm.ProviderCharm]:
    return ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
