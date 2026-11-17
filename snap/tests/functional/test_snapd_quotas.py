# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_quotas: set_quota, remove_quota, get_quota, list_quotas.

Alongside end-to-end tests of the public functions, this module pins the snapd behaviours
the quota design rests on (one test each, named after the behaviour), so that a change in
snapd shows up here rather than in a subtly broken ensure_quota.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from charmlibs import snap
from charmlibs.snap import _client
from conftest import QUOTA_TEST_PREFIX as _PREFIX
from conftest import ensure_installed_local, reset_service_rate_limit

# The locally-built test snaps (tests/functional/snaps). The first two have a single
# daemon service each; test-snap has no services.
_SNAP = 'test-service-snap'
_OTHER_SNAP = 'test-other-service-snap'
_NO_SERVICES_SNAP = 'test-snap'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'

_MiB = 1024**2


def _raw_ensure(
    group: str,
    *,
    snaps: list[str] | None = None,
    services: list[str] | None = None,
    parent: str | None = None,
    constraints: dict[str, Any] | None = None,
) -> None:
    """POST an ensure request directly, for the inputs the public functions refuse."""
    body: dict[str, Any] = {'action': 'ensure', 'group-name': group}
    if parent is not None:
        body['parent'] = parent
    if snaps:
        body['snaps'] = snaps
    if services:
        body['services'] = services
    if constraints:
        body['constraints'] = constraints
    _client.post('/v2/quotas', body=body)


def _service_start_stamp(name: str, service: str) -> str:
    """The time systemd last started the service, as an opaque comparable string.

    The monotonic variant is used because the wall-clock timestamp resolves to seconds,
    and a quota change and its restart can land within the same second.
    """
    out = subprocess.check_output([
        'systemctl',
        'show',
        f'snap.{name}.{service}',
        '-p',
        'ActiveEnterTimestampMonotonic',
    ])
    return out.decode().strip()


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


def test_set_get_list_remove_roundtrip():
    ensure_installed_local(_NO_SERVICES_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=4 * _MiB, cpu=(2, 50), threads=64)
    info = snap.get_quota(f'{_PREFIX}one')
    assert info.name == f'{_PREFIX}one'
    assert info.parent is None
    assert info.subgroups == []
    assert info.snaps == [_NO_SERVICES_SNAP]
    assert info.services == {}
    assert info.memory == 4 * _MiB
    assert info.cpu == (2, 50)
    assert info.cpu_set is None
    assert info.threads == 64
    # The snap has no running services, so nothing is counted against the limits.
    assert info.memory_usage == 0
    assert info.threads_usage == 0
    assert f'{_PREFIX}one' in [g.name for g in snap.list_quotas()]

    snap.remove_quota(f'{_PREFIX}one')
    with pytest.raises(snap.QuotaNotFoundError):
        snap.get_quota(f'{_PREFIX}one')
    assert f'{_PREFIX}one' not in [g.name for g in snap.list_quotas()]


def test_set_quota_cpu_percentage_only():
    ensure_installed_local(_NO_SERVICES_SNAP)
    # (None, 50) is the CLI's '50%': half of every available core, with no count sent.
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, cpu=(None, 50))
    info = snap.get_quota(f'{_PREFIX}one')
    assert info.cpu == (None, 50)
    assert info.cpu_set is None


def test_set_quota_cpu_set():
    ensure_installed_local(_NO_SERVICES_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, cpu_set=[0])
    info = snap.get_quota(f'{_PREFIX}one')
    assert info.cpu_set == [0]


def test_set_quota_services_in_subgroup():
    ensure_installed_local(_SNAP)
    reset_service_rate_limit(_SNAP, 'daemon')  # joining a group restarts the service
    # Services are quota'ed in a sub-group of the group their snap belongs to.
    snap.set_quota(f'{_PREFIX}svc', _SNAP, memory=4 * _MiB)
    snap.set_quota(
        f'{_PREFIX}svc-sub',
        services={_SNAP: ['daemon']},
        parent=f'{_PREFIX}svc',
        cpu=(None, 25),
    )
    info = snap.get_quota(f'{_PREFIX}svc-sub')
    assert info.parent == f'{_PREFIX}svc'
    assert info.snaps == []
    assert info.services == {_SNAP: ['daemon']}
    assert info.cpu == (None, 25)
    parent = snap.get_quota(f'{_PREFIX}svc')
    assert parent.subgroups == [f'{_PREFIX}svc-sub']


def test_list_quotas_empty():
    assert snap.list_quotas() == []


def test_set_quota_is_additive():
    ensure_installed_local(_NO_SERVICES_SNAP)
    ensure_installed_local(_OTHER_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=4 * _MiB)
    snap.set_quota(f'{_PREFIX}one', _OTHER_SNAP, threads=64)
    info = snap.get_quota(f'{_PREFIX}one')
    assert sorted(info.snaps) == sorted([_NO_SERVICES_SNAP, _OTHER_SNAP])
    assert info.memory == 4 * _MiB
    assert info.threads == 64


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_get_quota_not_found():
    with pytest.raises(snap.QuotaNotFoundError):
        snap.get_quota(f'{_PREFIX}absent')


def test_remove_quota_not_found():
    with pytest.raises(snap.QuotaNotFoundError):
        snap.remove_quota(f'{_PREFIX}absent')


def test_remove_quota_with_subgroups():
    snap.set_quota(f'{_PREFIX}parent', memory=4 * _MiB)
    snap.set_quota(f'{_PREFIX}parent-sub', parent=f'{_PREFIX}parent', memory=4 * _MiB)
    with pytest.raises(snap.QuotaHasSubgroupsError):
        snap.remove_quota(f'{_PREFIX}parent')
    # Nothing was changed: both groups are still there, and removing the sub-group
    # first lets the parent go.
    assert sorted(g.name for g in snap.list_quotas()) == [
        f'{_PREFIX}parent',
        f'{_PREFIX}parent-sub',
    ]
    snap.remove_quota(f'{_PREFIX}parent-sub')
    snap.remove_quota(f'{_PREFIX}parent')
    assert snap.list_quotas() == []


def test_set_quota_not_installed_snap():
    with pytest.raises(snap.NotInstalledError):
        snap.set_quota(f'{_PREFIX}one', _ABSENT_SNAP, memory=4 * _MiB)


def test_set_quota_not_installed_services_snap():
    with pytest.raises(snap.NotInstalledError):
        snap.set_quota(f'{_PREFIX}one', services={_ABSENT_SNAP: ['daemon']}, memory=4 * _MiB)


def test_set_quota_none_is_a_type_error():
    with pytest.raises(TypeError, match='ensure_quota'):
        snap.set_quota(f'{_PREFIX}one', memory=None)  # pyright: ignore[reportArgumentType]
    with pytest.raises(snap.QuotaNotFoundError):
        snap.get_quota(f'{_PREFIX}one')


def test_set_quota_invalid_values_make_no_group():
    with pytest.raises(ValueError, match='memory must be'):
        snap.set_quota(f'{_PREFIX}one', memory=0)
    with pytest.raises(ValueError, match='cpu percentage must be'):
        snap.set_quota(f'{_PREFIX}one', cpu=(None, 101))
    with pytest.raises(snap.QuotaNotFoundError):
        snap.get_quota(f'{_PREFIX}one')


# ---------------------------------------------------------------------------
# snapd behaviours the design depends on
# ---------------------------------------------------------------------------


def test_behaviour_ensure_raises_limits_and_changes_cpu_in_place():
    # Behaviour 1, the additive half: on an existing group, ensure can add a snap, add a
    # limit that was not set, raise memory, raise threads, and change CPU up or down.
    ensure_installed_local(_NO_SERVICES_SNAP)
    ensure_installed_local(_OTHER_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=4 * _MiB, cpu=(2, 50))
    snap.set_quota(f'{_PREFIX}one', _OTHER_SNAP, memory=8 * _MiB, threads=64)
    info = snap.get_quota(f'{_PREFIX}one')
    assert sorted(info.snaps) == sorted([_NO_SERVICES_SNAP, _OTHER_SNAP])
    assert info.memory == 8 * _MiB
    assert info.threads == 64
    snap.set_quota(f'{_PREFIX}one', cpu=(2, 75))  # up
    assert snap.get_quota(f'{_PREFIX}one').cpu == (2, 75)
    snap.set_quota(f'{_PREFIX}one', cpu=(None, 25))  # down, and back to all cores
    assert snap.get_quota(f'{_PREFIX}one').cpu == (None, 25)


def test_behaviour_ensure_cannot_lower_limits():
    # Behaviour 1, the restrictive half: lowering memory or threads fails, so those
    # changes need the group to be removed and created again (see ensure_quota).
    ensure_installed_local(_NO_SERVICES_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=8 * _MiB, threads=128)
    with pytest.raises(snap.APIError, match='cannot decrease memory limit'):
        snap.set_quota(f'{_PREFIX}one', memory=4 * _MiB)
    with pytest.raises(snap.APIError, match='cannot decrease thread limit'):
        snap.set_quota(f'{_PREFIX}one', threads=64)
    info = snap.get_quota(f'{_PREFIX}one')
    assert info.memory == 8 * _MiB
    assert info.threads == 128


def test_behaviour_snap_already_in_a_group_is_rejected():
    # Behaviour 2: naming a snap that is already in a group fails -- even the group
    # being updated. ensure_quota relies on this never being attempted silently.
    ensure_installed_local(_NO_SERVICES_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=4 * _MiB)
    snap.set_quota(f'{_PREFIX}two', memory=4 * _MiB)
    with pytest.raises(snap.APIError, match='already in quota group'):
        snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP)  # same group
    with pytest.raises(snap.APIError, match='already in quota group'):
        snap.set_quota(f'{_PREFIX}two', _NO_SERVICES_SNAP)  # another group


def test_behaviour_zero_limit_is_dropped():
    # Behaviour 3: a limit sent as zero is dropped, not rejected, so the existing value
    # stays. Sent raw, because the public functions refuse zero (ValueError).
    ensure_installed_local(_NO_SERVICES_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=4 * _MiB, threads=64)
    _raw_ensure(f'{_PREFIX}one', constraints={'memory': 0, 'threads': 0})
    info = snap.get_quota(f'{_PREFIX}one')
    assert info.memory == 4 * _MiB
    assert info.threads == 64


def test_behaviour_parent_is_ignored_for_an_existing_group():
    # Behaviour 4: parent places a group only at creation; later it is ignored.
    snap.set_quota(f'{_PREFIX}parent', memory=4 * _MiB)
    snap.set_quota(f'{_PREFIX}one', memory=4 * _MiB)
    snap.set_quota(f'{_PREFIX}one', parent=f'{_PREFIX}parent')
    assert snap.get_quota(f'{_PREFIX}one').parent is None
    assert snap.get_quota(f'{_PREFIX}parent').subgroups == []


def test_behaviour_cpu_count_and_percentage_are_replaced_together():
    # Behaviour 5: a percentage with no count resets the count to all cores...
    snap.set_quota(f'{_PREFIX}one', memory=4 * _MiB, cpu=(2, 50))
    snap.set_quota(f'{_PREFIX}one', cpu=(None, 75))
    assert snap.get_quota(f'{_PREFIX}one').cpu == (None, 75)
    # ...and a count with no percentage is rejected. Sent raw: the public functions
    # always send the pair together.
    with pytest.raises(snap.APIError):
        _raw_ensure(f'{_PREFIX}one', constraints={'cpu': {'count': 3}})


def test_behaviour_api_allows_cpu_percentage_over_100():
    # Behaviour 6: only the CLI caps the CPU percentage at 100. Sent raw, because the
    # public functions refuse (ValueError) -- snapd itself accepts it.
    _raw_ensure(f'{_PREFIX}one', constraints={'cpu': {'percentage': 150}, 'memory': 4 * _MiB})
    assert snap.get_quota(f'{_PREFIX}one').cpu == (None, 150)


def test_behaviour_group_with_subgroups_cannot_be_removed():
    # Behaviour 7, at the API level (the public remove_quota's classification of this
    # failure is covered by test_remove_quota_with_subgroups above).
    snap.set_quota(f'{_PREFIX}parent', memory=4 * _MiB)
    snap.set_quota(f'{_PREFIX}parent-sub', parent=f'{_PREFIX}parent', memory=4 * _MiB)
    with pytest.raises(snap.APIError, match='with sub-groups'):
        _client.post('/v2/quotas', body={'action': 'remove', 'group-name': f'{_PREFIX}parent'})
    assert sorted(g.name for g in snap.list_quotas()) == [
        f'{_PREFIX}parent',
        f'{_PREFIX}parent-sub',
    ]


def test_behaviour_removing_a_snap_drops_it_from_its_group():
    # Behaviour 8: removing a snap from the system drops it from its group; the group
    # stays. ensure_quota relies on this to put a reinstalled snap back.
    ensure_installed_local(_NO_SERVICES_SNAP)
    snap.set_quota(f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=4 * _MiB)
    snap.remove(_NO_SERVICES_SNAP)
    info = snap.get_quota(f'{_PREFIX}one')
    assert info.snaps == []
    assert info.memory == 4 * _MiB


def test_behaviour_errors_have_no_kind():
    # Behaviour 9: these failures are HTTP 400 with only a message, no kind -- which is
    # why the library classifies them by probing, never by kind or message matching.
    with pytest.raises(snap.APIError) as not_installed:
        _raw_ensure(f'{_PREFIX}one', snaps=[_ABSENT_SNAP], constraints={'memory': 4 * _MiB})
    with pytest.raises(snap.APIError) as remove_absent:
        _client.post('/v2/quotas', body={'action': 'remove', 'group-name': f'{_PREFIX}absent'})
    snap.set_quota(f'{_PREFIX}two', memory=8 * _MiB)
    with pytest.raises(snap.APIError) as lowered:
        snap.set_quota(f'{_PREFIX}two', memory=4 * _MiB)
    for error in (not_installed.value, remove_absent.value, lowered.value):
        assert error._kind == ''
        assert error._status_code == 400
        assert error.message


def test_behaviour_membership_changes_restart_services_but_raising_a_limit_does_not():
    # Behaviour 10: adding a snap to a group, and removing the group, restart the snap's
    # services as part of the change; raising a limit does not.
    ensure_installed_local(_SNAP)
    reset_service_rate_limit(_SNAP, 'daemon')
    snap.start(_SNAP, 'daemon')
    first = _service_start_stamp(_SNAP, 'daemon')
    snap.set_quota(f'{_PREFIX}one', _SNAP, memory=4 * _MiB)
    assert _service_start_stamp(_SNAP, 'daemon') != first  # restarted by joining the group
    joined = _service_start_stamp(_SNAP, 'daemon')
    snap.set_quota(f'{_PREFIX}one', memory=8 * _MiB)
    assert _service_start_stamp(_SNAP, 'daemon') == joined  # raising a limit doesn't restart
    snap.remove_quota(f'{_PREFIX}one')
    assert _service_start_stamp(_SNAP, 'daemon') != joined  # restarted again by the removal


def test_behaviour_constraints_round_trip_unchanged():
    # Behaviour 11: the constraints object snapd returns has the same shape the ensure
    # action accepts, and the CPU count and percentage come back as given, not as their
    # product. ensure_quota relies on both to carry over limits it wasn't asked about.
    ensure_installed_local(_NO_SERVICES_SNAP)
    snap.set_quota(
        f'{_PREFIX}one', _NO_SERVICES_SNAP, memory=4 * _MiB, cpu=(2, 50), cpu_set=[0, 1]
    )
    info = snap.get_quota(f'{_PREFIX}one')
    assert info.cpu == (2, 50)  # not, say, 1x100%
    snap.remove_quota(f'{_PREFIX}one')
    # Send the raw constraints back unchanged to re-create the group with the same limits.
    _raw_ensure(f'{_PREFIX}one', snaps=[_NO_SERVICES_SNAP], constraints=info._constraints)
    recreated = snap.get_quota(f'{_PREFIX}one')
    assert recreated._constraints == info._constraints
    assert recreated.snaps == [_NO_SERVICES_SNAP]
