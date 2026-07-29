#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for local snap installation via the snapd sideload API.

Exercises the provisional ack and install_local helpers in conftest, which are built directly
on _client internals and POST /v2/snaps with a multipart body.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import SNAPS_DIR, ack, ensure_removed, install_local

if TYPE_CHECKING:
    from pathlib import Path

# A signed store snap, for the assertion (ack) tests: those need a snap whose assertions the
# store will hand us, which a locally-built snap by definition has none of.
_STORE_SNAP = 'test-snapd-tools'

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
def store_snap_download(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Download a signed store snap and its assertions once for the session."""
    d = tmp_path_factory.mktemp(_STORE_SNAP)
    subprocess.run(
        ['snap', 'download', _STORE_SNAP, '--channel=stable', f'--target-directory={d}'],
        check=True,
        capture_output=True,
    )
    snap_file = next(d.glob(f'{_STORE_SNAP}_*.snap'))
    assert_file = next(d.glob(f'{_STORE_SNAP}_*.assert'))
    return snap_file, assert_file


@pytest.fixture(autouse=True)
def remove_store_snap():
    yield
    ensure_removed(_STORE_SNAP)


# ---------------------------------------------------------------------------
# Tests — strict-confined snap
# ---------------------------------------------------------------------------


def test_install_local(snap_v1: Path):
    ensure_removed('test-snap')
    install_local(snap_v1, dangerous=True)
    info = _snapd.list_one('test-snap')
    assert info.name == 'test-snap'
    assert info.version == '1.0'


def test_install_local_already_installed(snap_v1: Path):
    # Sideloading does not raise _AlreadyInstalledError when the snap is present.
    ensure_removed('test-snap')
    install_local(snap_v1, dangerous=True)
    install_local(snap_v1, dangerous=True)  # Second call must succeed.
    assert _snapd.list_one('test-snap').version == '1.0'


def test_install_local_upgrades(snap_v1: Path, snap_v2: Path):
    ensure_removed('test-snap')
    install_local(snap_v1, dangerous=True)
    assert _snapd.list_one('test-snap').version == '1.0'
    install_local(snap_v2, dangerous=True)
    assert _snapd.list_one('test-snap').version == '2.0'


def test_install_local_without_dangerous_raises(snap_v1: Path):
    ensure_removed('test-snap')
    with pytest.raises(_errors.APIError) as ctx:
        install_local(snap_v1)  # dangerous=False by default.
    assert 'cannot find signatures with metadata' in ctx.value.message
    assert ctx.value.kind == ''


# ---------------------------------------------------------------------------
# Tests — classic-confined snap
# ---------------------------------------------------------------------------


def test_install_local_classic_without_classic_flag_raises(classic_snap_v1: Path):
    ensure_removed('test-classic-snap')
    with pytest.raises(_errors.NeedsClassicError):
        install_local(classic_snap_v1, dangerous=True)


def test_install_local_classic(classic_snap_v1: Path):
    ensure_removed('test-classic-snap')
    install_local(classic_snap_v1, dangerous=True, classic=True)
    info = _snapd.list_one('test-classic-snap')
    assert info.name == 'test-classic-snap'
    assert info.version == '1.0'


# ---------------------------------------------------------------------------
# Tests — assertions (ack)
# ---------------------------------------------------------------------------


def test_ack_and_install(store_snap_download: tuple[Path, Path]):
    snap_file, assert_file = store_snap_download
    ensure_removed(_STORE_SNAP)
    ack(assert_file.read_bytes())
    install_local(snap_file)  # dangerous=False — assertions are in the DB.
    assert _snapd.list_one(_STORE_SNAP).name == _STORE_SNAP


def test_ack_is_idempotent(store_snap_download: tuple[Path, Path]):
    _, assert_file = store_snap_download
    ack(assert_file.read_bytes())
    ack(assert_file.read_bytes())  # Second call must not raise.
