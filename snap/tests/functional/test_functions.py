#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _functions: ensure."""

import pytest

from charmlibs.snap import _functions, _snapd_snaps as _snapd
from conftest import ensure_removed

# ---------------------------------------------------------------------------
# ensure: install path
# ---------------------------------------------------------------------------


def test_ensure_installs_if_not_present():
    ensure_removed('hello-world')
    did_something = _functions.ensure('hello-world')
    assert did_something is True
    assert _snapd.info('hello-world').name == 'hello-world'


def test_ensure_installs_at_default_channel():
    ensure_removed('hello-world')
    _functions.ensure('hello-world')
    assert _snapd.info('hello-world').channel == 'latest/stable'


def test_ensure_installs_at_specified_channel():
    ensure_removed('hello-world')
    _functions.ensure('hello-world', channel='latest/candidate')
    assert _snapd.info('hello-world').channel == 'latest/candidate'


def test_ensure_installs_at_specified_revision():
    ensure_removed('hello-world')
    _functions.ensure('hello-world', revision=28)
    assert _snapd.info('hello-world').revision == 28


def test_ensure_installs_classic():
    ensure_removed('charmcraft')
    _functions.ensure('charmcraft', classic=True)
    assert _snapd.info('charmcraft').classic is True


# ---------------------------------------------------------------------------
# ensure: no-op path (already installed, no change needed)
# ---------------------------------------------------------------------------


def test_ensure_no_op_if_already_installed():
    _functions.ensure('hello-world')
    did_something = _functions.ensure('hello-world')
    assert did_something is False


def test_ensure_no_op_returns_false():
    _functions.ensure('hello-world', channel='latest/stable')
    result = _functions.ensure('hello-world', channel='latest/stable')
    assert result is False


def test_ensure_no_op_with_normalized_channel_latest():
    _functions.ensure('hello-world', channel='latest/stable')
    # 'latest' normalizes to 'latest/stable'
    result = _functions.ensure('hello-world', channel='latest')
    assert result is False


def test_ensure_no_op_with_normalized_channel_stable():
    _functions.ensure('hello-world', channel='latest/stable')
    # 'stable' normalizes to 'latest/stable'
    result = _functions.ensure('hello-world', channel='stable')
    assert result is False


def test_ensure_no_op_wrong_classic_flag():
    # If confinement doesn't match requested classic, ensure does nothing
    # (it doesn't refresh when only the classic flag differs).
    _functions.ensure('charmcraft', classic=True)
    assert _snapd.info('charmcraft').classic is True
    # Passing classic=False when snap is installed classic → no change (returns False).
    result = _functions.ensure('charmcraft', classic=False)
    assert result is False
    # Snap is still installed as classic.
    assert _snapd.info('charmcraft').classic is True


# ---------------------------------------------------------------------------
# ensure: refresh path (installed but wrong channel/revision)
# ---------------------------------------------------------------------------


def test_ensure_refreshes_on_different_channel():
    _functions.ensure('hello-world', channel='latest/stable')
    assert _snapd.info('hello-world').channel == 'latest/stable'
    did_something = _functions.ensure('hello-world', channel='latest/candidate')
    assert did_something is True
    assert _snapd.info('hello-world').channel == 'latest/candidate'


def test_ensure_refreshes_on_different_revision():
    _functions.ensure('hello-world')
    original_revision = _snapd.info('hello-world').revision
    older_revision = original_revision - 1
    did_something = _functions.ensure('hello-world', revision=older_revision)
    assert did_something is True
    assert _snapd.info('hello-world').revision == older_revision


def test_ensure_no_op_same_revision():
    _functions.ensure('hello-world')
    current_revision = _snapd.info('hello-world').revision
    did_something = _functions.ensure('hello-world', revision=current_revision)
    assert did_something is False


# ---------------------------------------------------------------------------
# ensure: error path
# ---------------------------------------------------------------------------


def test_ensure_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _functions.ensure('hello-world', channel='latest/stable', revision=28)
