#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _functions: ensure, ensure_revision.

Tests are ordered to minimise snap install/remove churn.  All tests that need
hello-world *installed* run first, then install-from-removed tests, then error
paths, with charmcraft tests grouped together.
"""

import pytest

from charmlibs.snap import _errors, _functions
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# hello-world INSTALLED — no-op / refresh paths (snap stays present)
# ---------------------------------------------------------------------------


def test_ensure_revision_no_op_if_same_revision():
    ensure_installed('hello-world')
    current_revision = _snapd.info('hello-world').revision
    result = _functions.ensure_revision('hello-world', revision=int(current_revision))
    assert result is False


def test_ensure_revision_refreshes_on_different_revision():
    ensure_installed('hello-world')
    original_revision = _snapd.info('hello-world').revision
    older_revision = int(original_revision) - 1
    did_something = _functions.ensure_revision('hello-world', revision=older_revision)
    assert did_something is True
    assert _snapd.info('hello-world').revision == str(older_revision)


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


def test_ensure_refreshes_on_different_channel():
    ensure_installed('hello-world', channel='latest/stable')
    did_something = _functions.ensure('hello-world', channel='latest/candidate')
    assert did_something is True
    assert _snapd.info('hello-world').channel == 'latest/candidate'


def test_ensure_no_updates_available_returns_false():
    ensure_installed('hello-world', channel='latest/stable')
    # Already up-to-date — no updates available.
    result = _functions.ensure('hello-world', channel='latest/stable')
    assert result is False


# ---------------------------------------------------------------------------
# hello-world INSTALL — tests that install from a removed state
# ---------------------------------------------------------------------------


def test_ensure_revision_installs_if_not_present():
    ensure_removed('hello-world')
    did_something = _functions.ensure_revision('hello-world', revision=28)
    assert did_something is True
    assert _snapd.info('hello-world').revision == '28'


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


# ---------------------------------------------------------------------------
# hello-world error paths (snap removed)
# ---------------------------------------------------------------------------


def test_ensure_bad_channel_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.APIError):
        _functions.ensure('hello-world', channel='not/a/real/channel')


def test_ensure_revision_bad_revision_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.RevisionNotAvailableError):
        _functions.ensure_revision('hello-world', revision=99999999)


# ---------------------------------------------------------------------------
# charmcraft (classic) — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_ensure_revision_installs_classic():
    ensure_removed('charmcraft')
    _functions.ensure_revision('charmcraft', revision=0, classic=True)
    assert _snapd.info('charmcraft').classic is True


def test_ensure_needs_classic_raises():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.NeedsClassicError):
        _functions.ensure('charmcraft')


def test_ensure_installs_classic():
    ensure_removed('charmcraft')
    _functions.ensure('charmcraft', classic=True)
    assert _snapd.info('charmcraft').classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_ensure_bad_snap_name_raises():
    with pytest.raises(_errors.NotFoundError):
        _functions.ensure(_ABSENT_SNAP)


# ---------------------------------------------------------------------------
# ensure with channel='' — treated as no channel (empty string is falsy)
# ---------------------------------------------------------------------------


def test_ensure_empty_channel_installs_on_default_channel() -> None:
    ensure_removed('hello-world')
    did_something = _functions.ensure('hello-world', channel='')
    assert did_something is True
    assert _snapd.info('hello-world').channel == 'latest/stable'


def test_ensure_empty_channel_refreshes_when_installed() -> None:
    # channel='' is falsy, so ensure skips the channel-mismatch branch
    # and falls through to the update-check refresh (no-op here).
    ensure_installed('hello-world', channel='latest/stable')
    result = _functions.ensure('hello-world', channel='')
    assert result is False
