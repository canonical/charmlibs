#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for local snap installation via the snapd sideload API.

Includes a provisional install_local implementation built directly on _client internals,
exercising POST /v2/snaps with a multipart body.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from charmlibs.snap import _client, _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_removed

SNAPS_DIR = Path(__file__).parent / 'snaps'


# ---------------------------------------------------------------------------
# Provisional ack implementation
# ---------------------------------------------------------------------------


def ack(assertions_data: bytes) -> None:
    """Upload assertion(s) to snapd's local database (POST /v2/assertions)."""
    response = _client._request_raw('POST', '/v2/assertions', data=assertions_data)
    response_dict = json.loads(response.read())
    if response_dict.get('type') == 'error':
        raise _client._make_error(response_dict)


# ---------------------------------------------------------------------------
# Provisional install_local implementation
# ---------------------------------------------------------------------------


def install_local(path: Path, *, dangerous: bool = False, classic: bool = False) -> None:
    """Install a local snap file via the snapd sideload API (POST /v2/snaps)."""
    snap_data = path.read_bytes()
    boundary = uuid.uuid4().hex

    crlf = b'\r\n'

    def form_field(name: str, value: str) -> bytes:
        return (
            b'--'
            + boundary.encode()
            + crlf
            + b'Content-Disposition: form-data; name="'
            + name.encode()
            + b'"'
            + crlf
            + crlf
            + value.encode()
            + crlf
        )

    body = (
        b'--'
        + boundary.encode()
        + crlf
        + b'Content-Disposition: form-data; name="snap"; filename="'
        + path.name.encode()
        + b'"'
        + crlf
        + b'Content-Type: application/octet-stream'
        + crlf
        + crlf
        + snap_data
        + crlf
    )
    if dangerous:
        body += form_field('dangerous', 'true')
    if classic:
        body += form_field('classic', 'true')
    body += b'--' + boundary.encode() + b'--' + crlf

    headers = {
        'Accept': 'application/json',
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    }
    response = _client._request_raw('POST', '/v2/snaps', headers=headers, data=body)
    response_dict = json.loads(response.read())
    if response_dict.get('type') == 'error':
        raise _client._make_error(response_dict)
    _client._wait_for_change(response_dict['change'])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def snap_v1() -> Path:
    return SNAPS_DIR / 'test-snap_1.0.snap'


@pytest.fixture
def snap_v2() -> Path:
    return SNAPS_DIR / 'test-snap_2.0.snap'


@pytest.fixture
def classic_snap_v1() -> Path:
    return SNAPS_DIR / 'test-classic-snap_1.0.snap'


@pytest.fixture(autouse=True)
def remove_test_snap():
    yield
    ensure_removed('test-snap')


@pytest.fixture(autouse=True)
def remove_test_classic_snap():
    yield
    ensure_removed('test-classic-snap')


@pytest.fixture(scope='session')
def hello_world_download(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Download hello-world snap and assertions once for the session."""
    d = tmp_path_factory.mktemp('hello-world')
    subprocess.run(
        ['snap', 'download', 'hello-world', '--channel=stable', f'--target-directory={d}'],
        check=True,
        capture_output=True,
    )
    snap_file = next(d.glob('hello-world_*.snap'))
    assert_file = next(d.glob('hello-world_*.assert'))
    return snap_file, assert_file


@pytest.fixture(autouse=True)
def remove_hello_world():
    yield
    ensure_removed('hello-world')


# ---------------------------------------------------------------------------
# Tests — strict-confined snap
# ---------------------------------------------------------------------------


def test_install_local(snap_v1: Path):
    ensure_removed('test-snap')
    install_local(snap_v1, dangerous=True)
    info = _snapd.info('test-snap')
    assert info.name == 'test-snap'
    assert info.version == '1.0'


def test_install_local_already_installed(snap_v1: Path):
    # Sideloading does not raise SnapAlreadyInstalledError when the snap is present.
    ensure_removed('test-snap')
    install_local(snap_v1, dangerous=True)
    install_local(snap_v1, dangerous=True)  # second call must succeed
    assert _snapd.info('test-snap').version == '1.0'


def test_install_local_upgrades(snap_v1: Path, snap_v2: Path):
    ensure_removed('test-snap')
    install_local(snap_v1, dangerous=True)
    assert _snapd.info('test-snap').version == '1.0'
    install_local(snap_v2, dangerous=True)
    assert _snapd.info('test-snap').version == '2.0'


def test_install_local_without_dangerous_raises(snap_v1: Path):
    ensure_removed('test-snap')
    with pytest.raises(_errors.SnapAPIError) as ctx:
        install_local(snap_v1)  # dangerous=False by default
    assert 'cannot find signatures with metadata' in ctx.value.message
    assert ctx.value.kind == ''


# ---------------------------------------------------------------------------
# Tests — classic-confined snap
# ---------------------------------------------------------------------------


def test_install_local_classic_without_classic_flag_raises(classic_snap_v1: Path):
    ensure_removed('test-classic-snap')
    with pytest.raises(_errors.SnapNeedsClassicError):
        install_local(classic_snap_v1, dangerous=True)


def test_install_local_classic(classic_snap_v1: Path):
    ensure_removed('test-classic-snap')
    install_local(classic_snap_v1, dangerous=True, classic=True)
    info = _snapd.info('test-classic-snap')
    assert info.name == 'test-classic-snap'
    assert info.version == '1.0'


# ---------------------------------------------------------------------------
# Tests — assertions (ack)
# ---------------------------------------------------------------------------


def test_ack_and_install(hello_world_download: tuple[Path, Path]):
    snap_file, assert_file = hello_world_download
    ensure_removed('hello-world')
    ack(assert_file.read_bytes())
    install_local(snap_file)  # dangerous=False — assertions are in the DB
    assert _snapd.info('hello-world').name == 'hello-world'


def test_ack_is_idempotent(hello_world_download: tuple[Path, Path]):
    _, assert_file = hello_world_download
    ack(assert_file.read_bytes())
    ack(assert_file.read_bytes())  # second call must not raise
