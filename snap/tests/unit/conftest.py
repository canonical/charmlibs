# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from charmlibs.snap import _client

FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures'


@dataclass
class MockClient:
    get: MagicMock
    get_logs: MagicMock
    post: MagicMock
    put: MagicMock


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> MockClient:
    """Patch _client.get, .get_logs, .post, and .put for use in _snapd_*.py tests."""
    client = MockClient(get=MagicMock(), get_logs=MagicMock(), post=MagicMock(), put=MagicMock())
    monkeypatch.setattr(_client, 'get', client.get)
    monkeypatch.setattr(_client, 'get_logs', client.get_logs)
    monkeypatch.setattr(_client, 'post', client.post)
    monkeypatch.setattr(_client, 'put', client.put)
    return client


def load_fixture(name: str) -> Any:
    """Load a fixture file. Returns the full API envelope dict, or a list for logs_lxd.json."""
    return json.loads((FIXTURES_DIR / name).read_text())


def result_of(name: str) -> Any:
    """Return the 'result' field from a fixture — what _client.get/put returns for sync ops."""
    data = load_fixture(name)
    if isinstance(data, list):
        return data  # pyright: ignore[reportUnknownVariableType]
    return data['result']
