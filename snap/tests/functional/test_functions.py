#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _functions: ensure, ensure_revision."""

import pytest

from charmlibs.snap import _errors, _functions
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed

# ---------------------------------------------------------------------------
# ensure_revision: install path
# ---------------------------------------------------------------------------


def test_ensure_revision_installs_if_not_present():
    ensure_removed('hello-world')
    did_something = _functions.ensure_revision('hello-world', revision=28)
    assert did_something is True
    assert _snapd.info('hello-world').revision == '28'


def test_ensure_revision_installs_classic():
    ensure_removed('charmcraft')
    _functions.ensure_revision('charmcraft', revision=0, classic=True)
    assert _snapd.info('charmcraft').classic is True


# ---------------------------------------------------------------------------
# ensure_revision: no-op path
# ---------------------------------------------------------------------------


def test_ensure_revision_no_op_if_same_revision():
    ensure_installed('hello-world')
    current_revision = _snapd.info('hello-world').revision
    result = _functions.ensure_revision('hello-world', revision=int(current_revision))
    assert result is False


# ---------------------------------------------------------------------------
# ensure_revision: refresh path
# ---------------------------------------------------------------------------


def test_ensure_revision_refreshes_on_different_revision():
    ensure_installed('hello-world')
    original_revision = _snapd.info('hello-world').revision
    older_revision = int(original_revision) - 1
    did_something = _functions.ensure_revision('hello-world', revision=older_revision)
    assert did_something is True
    assert _snapd.info('hello-world').revision == str(older_revision)


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


def test_ensure_installs_classic():
    ensure_removed('charmcraft')
    _functions.ensure('charmcraft', classic=True)
    assert _snapd.info('charmcraft').classic is True


# ---------------------------------------------------------------------------
# ensure: no-op path (update=False)
# ---------------------------------------------------------------------------


def test_ensure_no_op_update_false():
    ensure_installed('hello-world', channel='latest/stable')
    result = _functions.ensure('hello-world', channel='latest/stable', update=False)
    assert result is False


def test_ensure_no_op_normalized_channel():
    ensure_installed('hello-world', channel='latest/stable')
    result = _functions.ensure('hello-world', channel='latest', update=False)
    assert result is False


def test_ensure_no_op_stable_normalized():
    ensure_installed('hello-world', channel='latest/stable')
    result = _functions.ensure('hello-world', channel='stable', update=False)
    assert result is False


# ---------------------------------------------------------------------------
# ensure: refresh path (channel mismatch)
# ---------------------------------------------------------------------------


def test_ensure_refreshes_on_different_channel():
    ensure_installed('hello-world', channel='latest/stable')
    did_something = _functions.ensure('hello-world', channel='latest/candidate')
    assert did_something is True
    assert _snapd.info('hello-world').channel == 'latest/candidate'


# ---------------------------------------------------------------------------
# ensure: update path (same channel, update=True)
# ---------------------------------------------------------------------------


def test_ensure_no_updates_available_returns_false():
    ensure_installed('hello-world', channel='latest/stable')
    # Already up-to-date — no updates available.
    result = _functions.ensure('hello-world', channel='latest/stable')
    assert result is False


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


def test_ensure_needs_classic_raises():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.SnapNeedsClassicError):
        _functions.ensure('charmcraft')
