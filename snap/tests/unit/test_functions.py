# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from charmlibs.snap import _functions, _snapd_quotas
from charmlibs.snap import _snapd_snaps as _snapd
from charmlibs.snap._errors import (
    APIError,
    NotInstalledError,
    QuotaHasSubgroupsError,
    QuotaNotFoundError,
    _NotFoundError,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from conftest import MockClient


def make_info(
    tracking: str = 'latest/stable',
    revision: int | str = 29,
    classic: bool = False,
    hold: str | None = None,
) -> _snapd.InstalledInfo:
    return _snapd.InstalledInfo(
        name='hello-world',
        tracking=tracking,
        revision=revision,
        version='6.4',
        classic=classic,
        hold=hold,
    )


@dataclass
class MockSnapd:
    list_one: MagicMock
    install: MagicMock
    refresh: MagicMock


@pytest.fixture
def mock_snapd(monkeypatch: pytest.MonkeyPatch) -> MockSnapd:
    mocks = MockSnapd(list_one=MagicMock(), install=MagicMock(), refresh=MagicMock())
    monkeypatch.setattr(_snapd, 'list_one', mocks.list_one)
    monkeypatch.setattr(_snapd, 'install', mocks.install)
    monkeypatch.setattr(_snapd, 'refresh', mocks.refresh)
    return mocks


class TestGetInfo:
    def test_installed(self, mock_snapd: MockSnapd):
        expected = make_info()
        mock_snapd.list_one.return_value = expected
        result = _functions._installed_info('hello-world')
        mock_snapd.list_one.assert_called_once_with('hello-world')
        assert result is expected

    def test_not_installed_returns_none(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.side_effect = NotInstalledError(
            'snap "hello-world" is not installed',
            kind='snap-not-found',
            value='',
            status_code=404,
            status='Not Found',
        )
        result = _functions._installed_info('hello-world')
        assert result is None


class TestEnsureInstalledInstalls:
    def test_not_installed(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        result = _functions.ensure_installed('hello-world')
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=None, classic=False
        )
        assert result is True

    def test_not_installed_channel(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        _functions.ensure_installed('hello-world', channel='edge')
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel='edge', revision=None, classic=False
        )

    def test_not_installed_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        result = _functions.ensure_installed('hello-world', revision=5)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=5, classic=False
        )
        assert result is True

    def test_not_installed_channel_and_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        _functions.ensure_installed('hello-world', channel='edge', revision=5)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel='edge', revision=5, classic=False
        )

    def test_not_installed_classic(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        _functions.ensure_installed('hello-world', classic=True)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=None, classic=True
        )


class TestEnsureInstalledChannel:
    def test_installed_different_channel(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='edge')
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='edge', revision=None, classic=False
        )
        assert result is True

    def test_installed_same_channel_update_true(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        mock_snapd.refresh.return_value = True
        result = _functions.ensure_installed('hello-world', channel='latest/stable')
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='latest/stable', classic=False
        )
        assert result is True

    def test_installed_same_channel_update_false(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='latest/stable', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_no_channel_update_false(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info()
        result = _functions.ensure_installed('hello-world', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_normalized_channel(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='stable', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_risk_only_channel_inherits_track(self, mock_snapd: MockSnapd):
        # 'edge' resolves to '3.6/edge' for a snap on the 3.6 track, not to 'latest/edge',
        # so a snap already on '3.6/edge' is left alone rather than refreshed every call.
        mock_snapd.list_one.return_value = make_info(tracking='3.6/edge')
        result = _functions.ensure_installed('hello-world', channel='edge', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_risk_only_channel_inherits_track_when_different(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='3.6/stable')
        result = _functions.ensure_installed('hello-world', channel='edge')
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='edge', revision=None, classic=False
        )
        assert result is True

    def test_no_updates_available_returns_false(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        mock_snapd.refresh.return_value = False
        result = _functions.ensure_installed('hello-world', channel='latest/stable')
        assert result is False

    def test_empty_channel_treated_as_none(self, mock_snapd: MockSnapd):
        # channel='' is falsy, so it's treated the same as channel=None:
        # no channel-mismatch refresh, and with update=False no refresh at all.
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False


class TestEnsureInstalledRevision:
    def test_installed_same_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(revision=5)
        result = _functions.ensure_installed('hello-world', revision=5)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    @pytest.mark.parametrize('revision', [5, '5'])
    def test_revision_may_be_int_or_str(self, mock_snapd: MockSnapd, revision: int | str):
        mock_snapd.list_one.return_value = make_info(revision=5)
        result = _functions.ensure_installed('hello-world', revision=revision)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_different_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(revision=5)
        result = _functions.ensure_installed('hello-world', revision=6)
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel=None, revision=6, classic=False
        )
        assert result is True

    def test_same_revision_different_channel_refreshes(self, mock_snapd: MockSnapd):
        # The revision is already installed, but the snap tracks the wrong channel, so it
        # still needs a refresh -- snapd moves the tracking channel without changing revision.
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable', revision=5)
        result = _functions.ensure_installed('hello-world', channel='edge', revision=5)
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='edge', revision=5, classic=False
        )
        assert result is True

    @pytest.mark.parametrize('update', [True, False])
    def test_update_ignored_when_revision_matches(self, mock_snapd: MockSnapd, update: bool):
        # A revision fully specifies what to install, so there's nothing to update to.
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable', revision=5)
        result = _functions.ensure_installed(
            'hello-world', channel='stable', revision=5, update=update
        )
        mock_snapd.refresh.assert_not_called()
        assert result is False


class TestEnsureInstalledClassic:
    def test_classic_passed_to_refresh(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        _functions.ensure_installed('hello-world', channel='edge', classic=True)
        assert mock_snapd.refresh.call_args.kwargs['classic'] is True

    def test_classic_passed_to_update_refresh(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        _functions.ensure_installed('hello-world', channel='latest/stable', classic=True)
        assert mock_snapd.refresh.call_args.kwargs['classic'] is True


########################################################
# ensure_quota                                         #
########################################################


def make_quota(
    name: str = 'my-group',
    *,
    parent: str | None = None,
    subgroups: Iterable[str] = (),
    snaps: Iterable[str] = (),
    services: dict[str, list[str]] | None = None,
    constraints: dict[str, Any] | None = None,
) -> _snapd_quotas.QuotaInfo:
    """Build a QuotaInfo from a group result in snapd's shape (omitting empty values)."""
    result: dict[str, Any] = {'group-name': name, 'constraints': constraints or {}}
    if parent is not None:
        result['parent'] = parent
    if subgroups:
        result['subgroups'] = list(subgroups)
    if snaps:
        result['snaps'] = list(snaps)
    if services:
        result['services'] = [
            f'{snap_name}.{service}'
            for snap_name, services_list in services.items()
            for service in services_list
        ]
    return _snapd_quotas.QuotaInfo._from_dict(result)


def _quota_not_found(group: str) -> QuotaNotFoundError:
    return QuotaNotFoundError(
        f'cannot find quota group "{group}"', kind='', value='', status_code=404
    )


def _not_installed(snap: str) -> _NotFoundError:
    # Mirrors snapd's GET /v2/snaps/{snap}: a terse message with the snap name in `value`.
    return _NotFoundError('snap not installed', kind='snap-not-found', value=snap, status_code=404)


@dataclass
class MockQuotas:
    get_quota: MagicMock
    remove_quota: MagicMock


@pytest.fixture
def mock_quotas(monkeypatch: pytest.MonkeyPatch) -> MockQuotas:
    mocks = MockQuotas(get_quota=MagicMock(), remove_quota=MagicMock())
    monkeypatch.setattr(_snapd_quotas, 'get_quota', mocks.get_quota)
    monkeypatch.setattr(_snapd_quotas, 'remove_quota', mocks.remove_quota)
    return mocks


def _posted_bodies(mock_client: MockClient) -> list[dict[str, Any]]:
    return [call.kwargs['body'] for call in mock_client.post.call_args_list]


class TestEnsureQuotaValidation:
    @pytest.mark.parametrize(
        'kwargs',
        [
            {'snaps': ['']},
            {'snaps': [' ']},
            {'snaps': ['a/b']},
            {'services': {'': ['serv1']}},
            {'services': {'a/b': ['serv1']}},
            {'services': {'snap-a': [' ']}},
            {'parent': ''},
            {'parent': ' '},
            {'parent': 'a/b'},
            {'memory': 0},
            {'memory': -1},
            {'threads': 0},
            {'cpu': (None, 0)},
            {'cpu': (None, 101)},
            {'cpu': (0, 50)},
            {'cpu_set': []},
            {'cpu_set': [0, -1]},
        ],
    )
    def test_value_error_without_request(
        self, mock_client: MockClient, mock_quotas: MockQuotas, kwargs: dict[str, Any]
    ):
        with pytest.raises(ValueError):
            _functions.ensure_quota('my-group', **kwargs)
        mock_quotas.get_quota.assert_not_called()
        mock_client.get.assert_not_called()
        mock_client.post.assert_not_called()

    def test_parent_error_label(self, mock_client: MockClient, mock_quotas: MockQuotas):
        with pytest.raises(ValueError, match='parent group name must not be empty'):
            _functions.ensure_quota('my-group', parent='')

    def test_parent_none_is_not_an_error(self, mock_client: MockClient, mock_quotas: MockQuotas):
        # None means 'must be absent' (a top-level group), not an invalid name.
        mock_quotas.get_quota.return_value = make_quota(constraints={'memory': 1024})
        result = _functions.ensure_quota('my-group', parent=None)
        assert not result


class TestEnsureQuotaNeedsALimit:
    def test_removing_the_only_limit_raises_without_a_write(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # Without the check, the group is removed and then snapd refuses to create it
        # again -- the caller gets an APIError and the group is gone.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a'], constraints={'memory': 1024}
        )
        with pytest.raises(ValueError, match='at least one limit'):
            _functions.ensure_quota('my-group', memory=None)
        mock_client.post.assert_not_called()
        mock_quotas.remove_quota.assert_not_called()

    def test_new_group_without_a_limit_raises_without_a_write(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        mock_quotas.get_quota.side_effect = _quota_not_found('my-group')
        with pytest.raises(ValueError, match='at least one limit'):
            _functions.ensure_quota('my-group', ['a'])
        mock_client.post.assert_not_called()
        mock_quotas.remove_quota.assert_not_called()

    def test_removing_the_only_library_limit_with_a_journal_quota_succeeds(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # A call made only of removals is not always an error: the journal entry, which
        # the library has no argument for, still counts as a limit.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a'], constraints={'memory': 1024, 'journal': {'size': 16777216}}
        )
        result = _functions.ensure_quota('my-group', memory=None)
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'snaps': ['a'],
                'constraints': {'journal': {'size': 16777216}},
            }
        ]


class TestEnsureQuotaCreate:
    def test_create_full_group(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.side_effect = _quota_not_found('my-group')
        result = _functions.ensure_quota(
            'my-group',
            ['snap-a', 'snap-b'],
            services={'snap-c': ['serv1'], 'snap-d': 'serv2'},
            parent='parent-group',
            memory=67108864,
            cpu=(2, 50),
            cpu_set=[0, 3],
            threads=32,
        )
        assert result
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'parent': 'parent-group',
                'snaps': ['snap-a', 'snap-b'],
                'services': ['snap-c.serv1', 'snap-d.serv2'],
                'constraints': {
                    'memory': 67108864,
                    'cpu': {'count': 2, 'percentage': 50},
                    'cpu-set': {'cpus': [0, 3]},
                    'threads': 32,
                },
            }
        ]
        mock_quotas.remove_quota.assert_not_called()

    def test_create_minimal_group(self, mock_client: MockClient, mock_quotas: MockQuotas):
        # What is not given is absent from a new group, and from the request.
        mock_quotas.get_quota.side_effect = _quota_not_found('my-group')
        result = _functions.ensure_quota('my-group', memory=1024)
        assert result
        assert _posted_bodies(mock_client) == [
            {'action': 'ensure', 'group-name': 'my-group', 'constraints': {'memory': 1024}}
        ]

    def test_create_cpu_without_count(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.side_effect = _quota_not_found('my-group')
        _functions.ensure_quota('my-group', cpu=(None, 50))
        body = mock_client.post.call_args.kwargs['body']
        assert body['constraints'] == {'cpu': {'percentage': 50}}

    def test_create_converts_not_installed(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.side_effect = _quota_not_found('my-group')
        mock_client.post.side_effect = APIError(
            'cannot use snap', kind='', value='', status_code=400
        )
        mock_client.get.side_effect = _not_installed('absent')
        with pytest.raises(NotInstalledError):
            _functions.ensure_quota('my-group', ['absent'], memory=1024)
        mock_quotas.remove_quota.assert_not_called()

    def test_create_reraises_original_when_snaps_installed(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        mock_quotas.get_quota.side_effect = _quota_not_found('my-group')
        original = APIError('cannot mix services and snaps', kind='', value='', status_code=400)
        mock_client.post.side_effect = original
        mock_client.get.return_value = {}  # every probed snap installed
        with pytest.raises(APIError) as ctx:
            _functions.ensure_quota('my-group', ['snap-a'], memory=1024)
        assert ctx.value is original


class TestEnsureQuotaNoChange:
    def test_no_change_makes_no_write(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(
            parent='parent-group',
            snaps=['snap-a'],
            constraints={'memory': 1024, 'cpu': {'percentage': 50}, 'threads': 4},
        )
        result = _functions.ensure_quota(
            'my-group',
            ['snap-a'],
            parent='parent-group',
            memory=1024,
            cpu=(None, 50),
            threads=4,
        )
        assert not result
        mock_client.post.assert_not_called()
        mock_quotas.remove_quota.assert_not_called()

    def test_order_is_ignored(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a', 'b'],
            services={'snap-c': ['s1', 's2']},
            constraints={'cpu-set': {'cpus': [0, 1]}},
        )
        result = _functions.ensure_quota(
            'my-group',
            ['b', 'a'],
            services={'snap-c': ['s2', 's1']},
            cpu_set=[1, 0],
        )
        assert not result
        mock_client.post.assert_not_called()

    def test_unchanged_arguments_are_never_compared(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # The group's snaps, services, parent, and limits all stay UNCHANGED, so nothing
        # is compared and nothing is sent -- whatever they are.
        mock_quotas.get_quota.return_value = make_quota(
            parent='parent-group',
            snaps=['snap-a'],
            constraints={'memory': 1024},
        )
        result = _functions.ensure_quota('my-group')
        assert not result
        mock_client.post.assert_not_called()

    def test_empty_cpu_set_entry_means_not_set(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # snapd reports cpu and cpu-set together whenever either is set, with the unused
        # one an empty object. The empty entry is not a limit that is set: cpu_set=None
        # on this group is already true, not a reason to re-create it.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a'], constraints={'cpu': {'percentage': 50}, 'cpu-set': {}}
        )
        result = _functions.ensure_quota('my-group', ['a'], cpu=(None, 50), cpu_set=None)
        assert not result
        mock_client.post.assert_not_called()
        mock_quotas.remove_quota.assert_not_called()

    def test_empty_cpu_entry_means_not_set(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # The mirror case: a group with only a CPU set is reported with an empty cpu entry.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a'], constraints={'cpu': {}, 'cpu-set': {'cpus': [0]}}
        )
        result = _functions.ensure_quota('my-group', ['a'], cpu=None, cpu_set=[0])
        assert not result
        mock_client.post.assert_not_called()
        mock_quotas.remove_quota.assert_not_called()


class TestEnsureQuotaUpdateInPlace:
    def test_add_snap_sends_only_the_new_snap(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # A snap already in the group is never re-sent: snapd rejects it as
        # 'snap already in quota group', even for the group being updated.
        mock_quotas.get_quota.return_value = make_quota(snaps=['a'], constraints={'memory': 1024})
        result = _functions.ensure_quota('my-group', ['a', 'b'])
        assert result
        assert _posted_bodies(mock_client) == [
            {'action': 'ensure', 'group-name': 'my-group', 'snaps': ['b']}
        ]

    def test_add_service_sends_only_the_new_service(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        mock_quotas.get_quota.return_value = make_quota(
            parent='parent-group',
            services={'snap-a': ['s1']},
            constraints={'memory': 1024},
        )
        result = _functions.ensure_quota('my-group', services={'snap-a': ['s1', 's2']})
        assert result
        assert _posted_bodies(mock_client) == [
            {'action': 'ensure', 'group-name': 'my-group', 'services': ['snap-a.s2']}
        ]

    def test_add_limit_sends_only_the_new_limit(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        mock_quotas.get_quota.return_value = make_quota(snaps=['a'], constraints={'memory': 1024})
        result = _functions.ensure_quota('my-group', threads=4)
        assert result
        assert _posted_bodies(mock_client) == [
            {'action': 'ensure', 'group-name': 'my-group', 'constraints': {'threads': 4}}
        ]

    def test_raise_memory(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(constraints={'memory': 1024})
        result = _functions.ensure_quota('my-group', memory=2048)
        assert result
        assert _posted_bodies(mock_client) == [
            {'action': 'ensure', 'group-name': 'my-group', 'constraints': {'memory': 2048}}
        ]

    def test_raise_threads(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(constraints={'threads': 4})
        result = _functions.ensure_quota('my-group', threads=8)
        assert result
        assert _posted_bodies(mock_client) == [
            {'action': 'ensure', 'group-name': 'my-group', 'constraints': {'threads': 8}}
        ]

    def test_cpu_changes_down_in_place(self, mock_client: MockClient, mock_quotas: MockQuotas):
        # The CPU limit may change in either direction without re-creating the group.
        mock_quotas.get_quota.return_value = make_quota(
            constraints={'cpu': {'count': 2, 'percentage': 50}}
        )
        result = _functions.ensure_quota('my-group', cpu=(None, 25))
        assert result
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'constraints': {'cpu': {'percentage': 25}},
            }
        ]
        mock_quotas.remove_quota.assert_not_called()

    def test_unchanged_limit_is_not_resent(self, mock_client: MockClient, mock_quotas: MockQuotas):
        # memory stays UNCHANGED, so the request carries only the new snap -- snapd would
        # keep the memory limit anyway, but re-sending it is not our business.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a'], constraints={'memory': 1024, 'threads': 4}
        )
        result = _functions.ensure_quota('my-group', ['a', 'b'], threads=4)
        assert result
        assert _posted_bodies(mock_client) == [
            {'action': 'ensure', 'group-name': 'my-group', 'snaps': ['b']}
        ]

    def test_update_converts_not_installed(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(snaps=['a'], constraints={'memory': 1024})
        mock_client.post.side_effect = APIError(
            'cannot use snap', kind='', value='', status_code=400
        )
        mock_client.get.side_effect = _not_installed('absent')
        with pytest.raises(NotInstalledError):
            _functions.ensure_quota('my-group', ['a', 'absent'])
        mock_quotas.remove_quota.assert_not_called()

    def test_update_reraises_original_when_snaps_installed(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        mock_quotas.get_quota.return_value = make_quota(snaps=['a'], constraints={'memory': 1024})
        original = APIError('cannot mix services and snaps', kind='', value='', status_code=400)
        mock_client.post.side_effect = original
        mock_client.get.return_value = {}  # every probed snap installed
        with pytest.raises(APIError) as ctx:
            _functions.ensure_quota('my-group', ['a', 'b'])
        assert ctx.value is original
        mock_quotas.remove_quota.assert_not_called()


class TestEnsureQuotaRecreate:
    def test_parent_differs_recreates(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(
            parent='old-parent', constraints={'memory': 1024}
        )
        result = _functions.ensure_quota('my-group', parent='new-parent')
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'parent': 'new-parent',
                'constraints': {'memory': 1024},
            }
        ]

    def test_becoming_top_level_recreates(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(
            parent='old-parent', constraints={'memory': 1024}
        )
        result = _functions.ensure_quota('my-group', parent=None)
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')
        body = mock_client.post.call_args.kwargs['body']
        assert 'parent' not in body

    def test_removed_snap_recreates(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a', 'b'], constraints={'memory': 1024}
        )
        result = _functions.ensure_quota('my-group', ['a'])
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'snaps': ['a'],
                'constraints': {'memory': 1024},
            }
        ]

    def test_removed_service_recreates(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(
            parent='parent-group',
            services={'snap-a': ['s1', 's2']},
            constraints={'memory': 1024},
        )
        result = _functions.ensure_quota('my-group', services={'snap-a': ['s1']})
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'parent': 'parent-group',
                'services': ['snap-a.s1'],
                'constraints': {'memory': 1024},
            }
        ]

    @pytest.mark.parametrize(
        ('dropped', 'kept'),
        [('memory', {'threads': 4}), ('threads', {'memory': 1024})],
    )
    def test_none_limit_recreates_and_drops_the_limit(
        self,
        mock_client: MockClient,
        mock_quotas: MockQuotas,
        dropped: str,
        kept: dict[str, int],
    ):
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a'], constraints={'memory': 1024, 'threads': 4}
        )
        kwargs: dict[str, Any] = {dropped: None}
        result = _functions.ensure_quota('my-group', **kwargs)
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'snaps': ['a'],
                'constraints': kept,
            }
        ]

    def test_lower_memory_recreates(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(constraints={'memory': 2048})
        result = _functions.ensure_quota('my-group', memory=1024)
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')

    def test_lower_threads_recreates(self, mock_client: MockClient, mock_quotas: MockQuotas):
        mock_quotas.get_quota.return_value = make_quota(constraints={'threads': 8})
        result = _functions.ensure_quota('my-group', threads=4)
        assert result
        mock_quotas.remove_quota.assert_called_once_with('my-group')

    def test_empty_snaps_recreates_with_no_snaps(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        mock_quotas.get_quota.return_value = make_quota(snaps=['a'], constraints={'memory': 1024})
        result = _functions.ensure_quota('my-group', ())
        assert result
        body = mock_client.post.call_args.kwargs['body']
        assert 'snaps' not in body
        assert body['constraints'] == {'memory': 1024}

    def test_recreate_keeps_unchanged_limits_and_unknown_constraints(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # memory and the journal entry (which the library has no argument for) are
        # UNCHANGED, so they are carried over to the re-created group untouched.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a', 'b'],
            constraints={'memory': 1024, 'threads': 4, 'journal': {'size': 16777216}},
        )
        result = _functions.ensure_quota('my-group', ['a'], threads=8)
        assert result
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'snaps': ['a'],
                'constraints': {'memory': 1024, 'threads': 8, 'journal': {'size': 16777216}},
            }
        ]

    def test_recreate_keeps_an_empty_journal_entry(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # Unlike cpu and cpu-set, an empty journal entry is meaningful (a journal quota
        # with no size or rate), so it is carried over like any other entry.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a', 'b'], constraints={'memory': 2048, 'journal': {}}
        )
        result = _functions.ensure_quota('my-group', ['a'])
        assert result
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'snaps': ['a'],
                'constraints': {'memory': 2048, 'journal': {}},
            }
        ]

    def test_recreate_keeps_unchanged_membership_and_parent(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        mock_quotas.get_quota.return_value = make_quota(
            parent='parent-group',
            services={'snap-a': ['s1']},
            constraints={'memory': 2048},
        )
        result = _functions.ensure_quota('my-group', memory=1024)
        assert result
        assert _posted_bodies(mock_client) == [
            {
                'action': 'ensure',
                'group-name': 'my-group',
                'parent': 'parent-group',
                'services': ['snap-a.s1'],
                'constraints': {'memory': 1024},
            }
        ]

    def test_wrong_snap_name_preserves_group(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # The target's snaps are checked before the group is removed, so a typo'd snap
        # name cannot delete a working group.
        mock_quotas.get_quota.return_value = make_quota(snaps=['a'], constraints={'memory': 2048})
        mock_client.get.side_effect = _not_installed('absent')
        with pytest.raises(NotInstalledError):
            _functions.ensure_quota('my-group', ['absent'], memory=1024)
        mock_quotas.remove_quota.assert_not_called()
        mock_client.post.assert_not_called()

    def test_subgroups_error_stops_recreate(
        self, mock_client: MockClient, mock_quotas: MockQuotas
    ):
        # A group with sub-groups cannot be re-created; the error escapes and the
        # create request is never made.
        mock_quotas.get_quota.return_value = make_quota(
            snaps=['a'], subgroups=['sub'], constraints={'memory': 2048}
        )
        mock_quotas.remove_quota.side_effect = QuotaHasSubgroupsError(
            'cannot remove quota group with sub-groups', kind='', value='', status_code=400
        )
        with pytest.raises(QuotaHasSubgroupsError):
            _functions.ensure_quota('my-group', memory=1024)
        mock_client.post.assert_not_called()
