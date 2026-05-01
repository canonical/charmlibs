# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures'


@dataclass
class MockClient:
    get: MagicMock
    post: MagicMock
    put: MagicMock


@pytest.fixture
def mock_client(mocker: MockerFixture) -> MockClient:
    """Patch _client.get, .post, and .put for use in _snapd_*.py tests."""
    return MockClient(
        get=mocker.patch('charmlibs.snap._client.get'),
        post=mocker.patch('charmlibs.snap._client.post'),
        put=mocker.patch('charmlibs.snap._client.put'),
    )


def load_fixture(name: str) -> Any:
    """Load a fixture file. Returns the full API envelope dict, or a list for logs_lxd.json."""
    return json.loads((FIXTURES_DIR / name).read_text())


def result_of(name: str) -> Any:
    """Return the 'result' field from a fixture — what _client.get/put returns for sync ops."""
    data = load_fixture(name)
    if isinstance(data, list):
        return data  # pyright: ignore[reportUnknownVariableType]
    return data['result']
