#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for local snap installation via the snapd sideload API.

Includes a provisional install_local implementation built directly on _client internals,
exercising POST /v2/snaps with a multipart body.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from charmlibs.snap import _client
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_removed

SNAPS_DIR = Path(__file__).parent / "snaps"


# ---------------------------------------------------------------------------
# Provisional install_local implementation
# ---------------------------------------------------------------------------


def install_local(path: Path, *, classic: bool = False) -> None:
    """Install a local snap file via the snapd sideload API (POST /v2/snaps)."""
    snap_data = path.read_bytes()
    boundary = uuid.uuid4().hex

    CRLF = b'\r\n'

    def form_field(name: str, value: str) -> bytes:
        return (
            b'--' + boundary.encode() + CRLF
            + b'Content-Disposition: form-data; name="' + name.encode() + b'"' + CRLF
            + CRLF
            + value.encode() + CRLF
        )

    body = (
        b'--' + boundary.encode() + CRLF
        + b'Content-Disposition: form-data; name="snap"; filename="' + path.name.encode() + b'"' + CRLF
        + b'Content-Type: application/octet-stream' + CRLF
        + CRLF
        + snap_data
        + CRLF
        + form_field("dangerous", "true")
    )
    if classic:
        body += form_field("classic", "true")
    else:
        body += form_field("devmode", "true")
    body += b'--' + boundary.encode() + b'--' + CRLF

    headers = {
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    response = _client._request_raw("POST", "/v2/snaps", headers=headers, data=body)
    response_dict = json.loads(response.read())
    if response_dict.get("type") == "error":
        raise _client._make_error(response_dict)
    _client._wait_for_change(response_dict["change"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def snap_v1() -> Path:
    return SNAPS_DIR / "test-snap_1.0.snap"


@pytest.fixture
def snap_v2() -> Path:
    return SNAPS_DIR / "test-snap_2.0.snap"


@pytest.fixture(autouse=True)
def remove_test_snap():
    yield
    ensure_removed("test-snap")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_install_local(snap_v1: Path):
    ensure_removed("test-snap")
    install_local(snap_v1)
    info = _snapd.info("test-snap")
    assert info.name == "test-snap"
    assert info.version == "1.0"


def test_install_local_already_installed(snap_v1: Path):
    # Sideloading does not raise SnapAlreadyInstalledError when the snap is present.
    ensure_removed("test-snap")
    install_local(snap_v1)
    install_local(snap_v1)  # second call must succeed
    assert _snapd.info("test-snap").version == "1.0"


def test_install_local_upgrades(snap_v1: Path, snap_v2: Path):
    ensure_removed("test-snap")
    install_local(snap_v1)
    assert _snapd.info("test-snap").version == "1.0"
    install_local(snap_v2)
    assert _snapd.info("test-snap").version == "2.0"
