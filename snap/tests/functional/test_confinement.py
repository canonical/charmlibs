#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for what the ``classic`` argument does, and what it does not do.

``classic`` is permission, not a choice of confinement. snapd takes confinement from the
revision's own ``snap.yaml`` and uses the flag only to check the caller consented to a revision
that requires it (``ensureInstallPreconditions`` in snapd's ``overlord/snapstate/snapstate.go``):
an installed classic snap keeps classic confinement on refresh without the flag, and the flag is
dropped for a revision that doesn't require it. So confinement follows the revision both ways,
and no value of ``classic`` changes the confinement of a revision already installed -- which is
why :func:`charmlibs.snap.ensure_installed` doesn't compare it against a snap's current
confinement.

These need one snap name whose revisions differ in confinement, so they use locally-built snaps:
``test-conf-snap`` 1.0 is strict, 2.0 and 3.0 are classic. Sideloading reaches the same flag
logic in snapd as a store install or refresh.
"""

from __future__ import annotations

import pytest

from charmlibs import snap
from charmlibs.snap import _errors
from conftest import SNAPS_DIR, ensure_removed, install_local

_SNAP = 'test-conf-snap'
_STRICT = SNAPS_DIR / f'{_SNAP}_1.0.snap'
_CLASSIC = SNAPS_DIR / f'{_SNAP}_2.0.snap'
_CLASSIC_2 = SNAPS_DIR / f'{_SNAP}_3.0.snap'


@pytest.fixture(autouse=True)
def remove_conf_snap():
    ensure_removed(_SNAP)
    yield
    ensure_removed(_SNAP)


def test_strict_revision_installs_without_the_flag():
    install_local(_STRICT, dangerous=True)
    info = snap.list_one(_SNAP)
    assert info.version == '1.0'
    assert info.classic is False


def test_refresh_to_a_classic_revision_needs_the_flag():
    # The one case the flag exists for: the installed revision doesn't require classic
    # confinement and the target revision does, so snapd asks the caller to consent.
    install_local(_STRICT, dangerous=True)
    with pytest.raises(_errors.NeedsClassicError) as ctx:
        install_local(_CLASSIC, dangerous=True, classic=False)
    assert ctx.value._kind == 'snap-needs-classic'
    assert snap.list_one(_SNAP).classic is False  # Unchanged by the failed refresh.


def test_refresh_to_a_classic_revision_with_the_flag():
    install_local(_STRICT, dangerous=True)
    install_local(_CLASSIC, dangerous=True, classic=True)
    info = snap.list_one(_SNAP)
    assert info.version == '2.0'
    assert info.classic is True


def test_classic_snap_stays_classic_on_refresh_without_the_flag():
    # snapd ORs the installed snap's classic flag into the request, so a charm that passed
    # classic=True on first install doesn't have to keep passing it on every later refresh.
    install_local(_CLASSIC, dangerous=True, classic=True)
    install_local(_CLASSIC_2, dangerous=True, classic=False)
    info = snap.list_one(_SNAP)
    assert info.version == '3.0'
    assert info.classic is True


def test_confinement_follows_the_revision_back_to_strict():
    # The other direction, and without any flag to ask for it: confinement is a property of the
    # revision, so refreshing a classic snap to a strict revision makes it strict again.
    install_local(_CLASSIC, dangerous=True, classic=True)
    assert snap.list_one(_SNAP).classic is True
    install_local(_STRICT, dangerous=True, classic=False)
    info = snap.list_one(_SNAP)
    assert info.version == '1.0'
    assert info.classic is False


def test_flag_is_silently_dropped_for_a_strict_revision():
    # Asking for classic confinement on a revision that doesn't need it is not an error, and
    # doesn't grant it: snapd drops the flag. So `classic=True` can never make a snap classic.
    install_local(_STRICT, dangerous=True, classic=True)
    assert snap.list_one(_SNAP).classic is False


def test_ensure_installed_does_not_refresh_an_installed_snap_to_change_confinement():
    # The library-level consequence: a strict snap that is already on the requested revision is
    # left alone even when classic=True is passed, because a refresh could not make it classic.
    install_local(_STRICT, dangerous=True)
    revision = snap.list_one(_SNAP).revision
    assert snap.ensure_installed(_SNAP, revision=revision, classic=True) is False
    info = snap.list_one(_SNAP)
    assert info.revision == revision
    assert info.classic is False
