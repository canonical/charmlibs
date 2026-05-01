# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import pytest

from charmlibs.snap import _snapd_snaps as _snapd
from charmlibs.snap._errors import (
    SnapAlreadyInstalledError,
    SnapError,
    SnapNotFoundError,
    SnapNoUpdatesAvailableError,
)
from conftest import result_of

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from conftest import MockClient


def _make_snap_not_found():
    return SnapNotFoundError(
        'snap "hello-world" is not installed',
        kind='snap-not-installed',
        value='',
        status_code=404,
        status='Not Found',
    )


def _minimal_info_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'name': 'hello-world',
        'version': '6.4',
        'channel': 'latest/stable',
        'revision': '29',
        'confinement': 'strict',
    }
    base.update(overrides)
    return base


class TestInfoFromDict:
    def test_basic_fields(self):
        info = _snapd.Info._from_dict(_minimal_info_dict())
        assert info.name == 'hello-world'
        assert info.version == '6.4'
        assert info.channel == 'latest/stable'
        assert info.revision == 29
        assert info.classic is False
        assert info.hold is None

    def test_revision_is_int(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(revision='29'))
        assert isinstance(info.revision, int)
        assert info.revision == 29

    def test_strict_not_classic(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(confinement='strict'))
        assert info.classic is False

    def test_devmode_not_classic(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(confinement='devmode'))
        assert info.classic is False

    def test_classic(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(confinement='classic'))
        assert info.classic is True

    def test_hold_present(self):
        info = _snapd.Info._from_dict(result_of('snap_info_hello_world_held.json'))
        assert info.hold is not None
        assert info.hold.year == 2318

    def test_hold_absent(self):
        info = _snapd.Info._from_dict(_minimal_info_dict())
        assert info.hold is None

    def test_extra_fields_ignored(self):
        d = _minimal_info_dict()
        d.update({
            'tracking-channel': 'latest/stable',
            'type': 'app',
            'devmode': False,
            'jailmode': False,
            'enabled': True,
            'status': 'active',
        })
        info = _snapd.Info._from_dict(d)
        assert info.name == 'hello-world'


class TestInfo:
    def test_info_installed(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        info = _snapd.info('hello-world')
        assert info.name == 'hello-world'
        assert info.revision == 29
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    def test_info_classic(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_kube_proxy.json')
        info = _snapd.info('kube-proxy')
        assert info.classic is True

    def test_info_with_hold(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world_held.json')
        info = _snapd.info('hello-world')
        assert info.hold is not None

    def test_info_missing_ok_false(self, mock_client: MockClient):
        mock_client.get.side_effect = _make_snap_not_found()
        with pytest.raises(SnapNotFoundError):
            _snapd.info('hello-world')

    def test_info_missing_ok_true(self, mock_client: MockClient):
        mock_client.get.side_effect = _make_snap_not_found()
        result = _snapd.info('hello-world', missing_ok=True)
        assert result is None

    def test_info_other_error_propagates(self, mock_client: MockClient):
        mock_client.get.side_effect = SnapError(
            'internal error',
            kind='internal-error',
            value='',
            status_code=500,
            status='Internal Server Error',
        )
        with pytest.raises(SnapError):
            _snapd.info('hello-world', missing_ok=True)


class TestInstall:
    def test_install_minimal(self, mock_client: MockClient):
        _snapd.install('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'install'}
        )

    def test_install_channel(self, mock_client: MockClient):
        _snapd.install('hello-world', channel='edge')
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'

    def test_install_revision(self, mock_client: MockClient):
        _snapd.install('hello-world', revision=5)
        body = mock_client.post.call_args.kwargs['body']
        assert body['revision'] == '5'  # sent as string per snapd API convention

    def test_install_classic(self, mock_client: MockClient):
        _snapd.install('hello-world', classic=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['classic'] is True

    def test_install_no_extras(self, mock_client: MockClient):
        _snapd.install('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert 'channel' not in body
        assert 'revision' not in body
        assert 'classic' not in body

    def test_install_both_raises(self, mock_client: MockClient):
        with pytest.raises(ValueError):
            _snapd.install('hello-world', channel='edge', revision=5)
        mock_client.post.assert_not_called()

    def test_install_already_installed_suppressed_by_default(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapAlreadyInstalledError('', kind='', value='')
        _snapd.install('hello-world')  # should not raise

    def test_install_already_installed_strict_raises(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapAlreadyInstalledError('', kind='', value='')
        with pytest.raises(SnapAlreadyInstalledError):
            _snapd.install('hello-world', strict=True)


class TestRemove:
    def test_remove(self, mock_client: MockClient):
        _snapd.remove('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'remove'}
        )

    def test_remove_no_purge_by_default(self, mock_client: MockClient):
        _snapd.remove('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert 'purge' not in body

    def test_remove_purge(self, mock_client: MockClient):
        _snapd.remove('hello-world', purge=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['purge'] is True

    def test_remove_not_installed_suppressed_by_default(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNotFoundError('', kind='', value='')
        _snapd.remove('hello-world')  # should not raise

    def test_remove_not_installed_strict_raises(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNotFoundError('', kind='', value='')
        with pytest.raises(SnapNotFoundError):
            _snapd.remove('hello-world', strict=True)


class TestRefresh:
    def test_refresh_minimal(self, mock_client: MockClient):
        _snapd.refresh('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert body == {'action': 'refresh'}

    def test_refresh_channel(self, mock_client: MockClient):
        _snapd.refresh('hello-world', channel='edge')
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'

    def test_refresh_revision(self, mock_client: MockClient):
        _snapd.refresh('hello-world', revision=42)
        body = mock_client.post.call_args.kwargs['body']
        assert body['revision'] == '42'

    def test_refresh_both_raises(self, mock_client: MockClient):
        with pytest.raises(ValueError):
            _snapd.refresh('hello-world', channel='edge', revision=42)

    def test_refresh_suppresses_no_updates(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNoUpdatesAvailableError(
            'snap "hello-world" has no updates available',
            kind='snap-no-update-available',
            value='',
            status_code=400,
            status='Bad Request',
        )
        _snapd.refresh('hello-world')  # should not raise

    def test_refresh_no_updates_suppressed_by_default(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNoUpdatesAvailableError('', kind='', value='')
        _snapd.refresh('hello-world')  # should not raise

    def test_refresh_no_updates_strict_raises(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNoUpdatesAvailableError('', kind='', value='')
        with pytest.raises(SnapNoUpdatesAvailableError):
            _snapd.refresh('hello-world', strict=True)


class TestHold:
    @pytest.fixture(autouse=True)
    def mock_info(self, mocker: MockerFixture):
        mocker.patch('charmlibs.snap._snapd_snaps.info')

    def test_hold_forever(self, mock_client: MockClient):
        _snapd.hold('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert body['time'] == 'forever'

    def test_hold_action_level(self, mock_client: MockClient):
        _snapd.hold('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert body['action'] == 'hold'
        assert body['hold-level'] == 'general'

    def test_hold_timedelta(self, mock_client: MockClient):
        before = datetime.datetime.now(datetime.timezone.utc)
        _snapd.hold('hello-world', duration=datetime.timedelta(days=2))
        body = mock_client.post.call_args.kwargs['body']
        assert body['time'] != 'forever'
        hold_time = datetime.datetime.fromisoformat(body['time'])
        assert hold_time > before + datetime.timedelta(days=1)

    def test_hold_int_seconds(self, mock_client: MockClient):
        before = datetime.datetime.now(datetime.timezone.utc)
        _snapd.hold('hello-world', duration=172800)  # 2 days in seconds
        body = mock_client.post.call_args.kwargs['body']
        hold_time = datetime.datetime.fromisoformat(body['time'])
        assert hold_time > before + datetime.timedelta(days=1)

    def test_hold_float_seconds(self, mock_client: MockClient):
        before = datetime.datetime.now(datetime.timezone.utc)
        _snapd.hold('hello-world', duration=172800.0)
        body = mock_client.post.call_args.kwargs['body']
        hold_time = datetime.datetime.fromisoformat(body['time'])
        assert hold_time > before + datetime.timedelta(days=1)

    def test_hold_not_installed(self, mock_client: MockClient, mocker: MockerFixture):
        snap_not_found = SnapNotFoundError('', kind='', value='')
        mocker.patch('charmlibs.snap._snapd_snaps.info', side_effect=snap_not_found)
        with pytest.raises(SnapNotFoundError):
            _snapd.hold('hello-world')
        mock_client.post.assert_not_called()


class TestUnhold:
    def test_unhold(self, mock_client: MockClient):
        _snapd.unhold('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'unhold'}
        )


class TestListSnaps:
    def test_list_snaps_returns_info_objects(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snaps_list.json')
        snaps = _snapd._list_snaps()
        assert len(snaps) == 2
        assert all(isinstance(s, _snapd.Info) for s in snaps)
        mock_client.get.assert_called_once_with('/v2/snaps')

    def test_list_snaps_names(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snaps_list.json')
        snaps = _snapd._list_snaps()
        assert {s.name for s in snaps} == {'hello-world', 'kube-proxy'}


class TestListChannels:
    def test_list_channels_returns_info_per_channel(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('find_hello_world.json')
        channels = _snapd._list_channels('hello-world')
        assert set(channels) == {'latest/stable', 'latest/candidate', 'latest/beta', 'latest/edge'}
        assert all(isinstance(v, _snapd.Info) for v in channels.values())
        mock_client.get.assert_called_once_with('/v2/find', query={'name': 'hello-world'})

    def test_list_channels_info_fields(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('find_hello_world.json')
        channels = _snapd._list_channels('hello-world')
        info = channels['latest/stable']
        assert info.name == 'hello-world'
        assert info.revision == 29
        assert info.classic is False
