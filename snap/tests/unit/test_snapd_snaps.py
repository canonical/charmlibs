# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from charmlibs.snap import _snapd_snaps as _snapd
from charmlibs.snap._errors import (
    Error,
    NotFoundError,
    NotInstalledError,
    _AlreadyInstalledError,
    _NoUpdatesAvailableError,
)
from conftest import result_of

if TYPE_CHECKING:
    from conftest import MockClient


def _make_snap_not_found():
    return NotFoundError(
        'snap "hello-world" is not installed',
        kind='snap-not-found',
        value='',
        status_code=404,
        status='Not Found',
    )


_MINIMAL_INFO_DICT: dict[str, Any] = {
    'name': 'hello-world',
    'version': '6.4',
    'channel': 'stable',
    'tracking-channel': 'latest/stable',
    'revision': '29',
    'confinement': 'strict',
}


class TestInfoFromDict:
    def test_basic_fields(self):
        info = _snapd.Info._from_dict(_MINIMAL_INFO_DICT)
        assert info.name == 'hello-world'
        assert info.version == '6.4'
        assert info.channel == 'latest/stable'
        assert info.revision == '29'
        assert info.classic is False
        assert info.hold is None

    def test_local_revision(self):
        info = _snapd.Info._from_dict({**_MINIMAL_INFO_DICT, 'revision': 'x1'})
        assert info.revision == 'x1'

    def test_channel_is_the_tracking_channel(self):
        # 'channel' is the channel the installed revision came from, which can differ from the
        # channel the snap tracks -- installing a revision without a channel tracks
        # latest/stable but sources the revision from wherever it's available.
        info = _snapd.Info._from_dict({
            **_MINIMAL_INFO_DICT,
            'channel': 'edge',
            'tracking-channel': 'latest/stable',
        })
        assert info.channel == 'latest/stable'

    def test_channel_empty_when_no_tracking_channel(self):
        # A snap installed from a local file tracks no channel: snapd omits the field entirely.
        info_dict = {k: v for k, v in _MINIMAL_INFO_DICT.items() if k != 'tracking-channel'}
        info = _snapd.Info._from_dict({**info_dict, 'channel': ''})
        assert info.channel == ''

    @pytest.mark.parametrize('confinement', ['strict', 'devmode'])
    def test_non_classic_confinement(self, confinement: str):
        info = _snapd.Info._from_dict({**_MINIMAL_INFO_DICT, 'confinement': confinement})
        assert info.classic is False

    def test_classic_confinement(self):
        info = _snapd.Info._from_dict({**_MINIMAL_INFO_DICT, 'confinement': 'classic'})
        assert info.classic is True

    def test_hold_present(self):
        info = _snapd.Info._from_dict(result_of('snap_info_hello_world_held.json'))
        assert info.hold is not None
        assert info.hold.year == 2318

    def test_extra_fields_ignored(self):
        info_dict: dict[str, Any] = {
            **_MINIMAL_INFO_DICT,
            'type': 'app',
            'devmode': False,
            'jailmode': False,
            'enabled': True,
            'status': 'active',
        }
        info = _snapd.Info._from_dict(info_dict)
        assert info.name == 'hello-world'


class TestInfo:
    def test_info_installed(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        info = _snapd.info('hello-world')
        assert info.name == 'hello-world'
        assert info.revision == '29'
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    def test_info_classic(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_kube_proxy.json')
        info = _snapd.info('kube-proxy')
        assert info.classic is True

    def test_info_with_hold(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world_held.json')
        info = _snapd.info('hello-world')
        assert info.hold is not None

    def test_info_missing_raises(self, mock_client: MockClient):
        mock_client.get.side_effect = _make_snap_not_found()
        with pytest.raises(NotFoundError):
            _snapd.info('hello-world')

    def test_info_other_error_propagates(self, mock_client: MockClient):
        mock_client.get.side_effect = Error(
            'internal error',
            kind='internal-error',
            value='',
            status_code=500,
            status='Internal Server Error',
        )
        with pytest.raises(Error):
            _snapd.info('hello-world')


class TestInstall:
    def test_install_minimal(self, mock_client: MockClient):
        result = _snapd.install('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'install'}
        )
        assert result is True

    def test_install_passes_channel_and_classic(self, mock_client: MockClient):
        _snapd.install('hello-world', channel='edge', classic=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'
        assert body['classic'] is True

    def test_install_revision(self, mock_client: MockClient):
        _snapd.install('hello-world', revision=5)
        body = mock_client.post.call_args.kwargs['body']
        assert body['revision'] == '5'  # Sent as string per snapd API convention.

    def test_install_channel_and_revision(self, mock_client: MockClient):
        # Not mutually exclusive: snapd installs the revision and tracks the channel, and
        # errors if the revision isn't available on that channel.
        _snapd.install('hello-world', channel='edge', revision=5)
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'
        assert body['revision'] == '5'

    def test_install_already_installed_returns_false(self, mock_client: MockClient):
        mock_client.post.side_effect = _AlreadyInstalledError('', kind='', value='')
        result = _snapd.install('hello-world')
        assert result is False


class TestRemove:
    def test_remove(self, mock_client: MockClient):
        result = _snapd.remove('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'remove'}
        )
        assert result is True

    def test_remove_purge(self, mock_client: MockClient):
        _snapd.remove('hello-world', purge=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['purge'] is True

    @pytest.mark.parametrize('purge', [False, True])
    def test_remove_not_installed_returns_false(self, mock_client: MockClient, purge: bool):
        mock_client.post.side_effect = NotInstalledError('', kind='snap-not-installed', value='')
        assert _snapd.remove('hello-world', purge=purge) is False


class TestRefresh:
    def test_refresh_minimal(self, mock_client: MockClient):
        result = _snapd.refresh('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert body == {'action': 'refresh'}
        assert result is True

    def test_refresh_channel(self, mock_client: MockClient):
        _snapd.refresh('hello-world', channel='edge')
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'

    def test_refresh_revision(self, mock_client: MockClient):
        _snapd.refresh('hello-world', revision=42)
        body = mock_client.post.call_args.kwargs['body']
        assert body['revision'] == '42'

    def test_refresh_channel_and_revision(self, mock_client: MockClient):
        _snapd.refresh('hello-world', channel='edge', revision=42)
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'
        assert body['revision'] == '42'

    def test_refresh_classic(self, mock_client: MockClient):
        _snapd.refresh('hello-world', classic=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['classic'] is True

    def test_refresh_classic_omitted_by_default(self, mock_client: MockClient):
        _snapd.refresh('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert 'classic' not in body

    def test_refresh_no_updates_returns_false(self, mock_client: MockClient):
        mock_client.post.side_effect = _NoUpdatesAvailableError(
            'snap "hello-world" has no updates available',
            kind='snap-no-update-available',
            value='',
            status_code=400,
            status='Bad Request',
        )
        result = _snapd.refresh('hello-world')
        assert result is False


class TestHold:
    @pytest.fixture(autouse=True)
    def mock_info(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(_snapd, 'info', MagicMock())

    def test_hold_forever_by_default(self, mock_client: MockClient):
        _snapd.hold('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert body['action'] == 'hold'
        assert body['hold-level'] == 'general'
        assert body['time'] == 'forever'

    @pytest.mark.parametrize('duration', [datetime.timedelta(days=2), 172800, 172800.0])
    def test_hold_duration(
        self, mock_client: MockClient, duration: datetime.timedelta | int | float
    ):
        before = datetime.datetime.now(datetime.timezone.utc)
        _snapd.hold('hello-world', duration=duration)  # Each value expresses 2 days.
        body = mock_client.post.call_args.kwargs['body']
        assert body['time'] != 'forever'
        hold_time = datetime.datetime.fromisoformat(body['time'])
        assert hold_time > before + datetime.timedelta(days=1)

    def test_hold_not_installed(self, mock_client: MockClient, monkeypatch: pytest.MonkeyPatch):
        snap_not_found = NotFoundError('', kind='snap-not-found', value='')
        monkeypatch.setattr(_snapd, 'info', MagicMock(side_effect=snap_not_found))
        with pytest.raises(NotFoundError):
            _snapd.hold('hello-world')
        mock_client.post.assert_not_called()


class TestUnhold:
    def test_unhold(self, mock_client: MockClient):
        _snapd.unhold('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'unhold'}
        )


_PATH_FUNCTIONS = [_snapd.info, _snapd.install, _snapd.remove, _snapd.refresh, _snapd.unhold]


class TestSnapNameInPath:
    # Every one of these interpolates the snap name into the URL path, so the name is validated
    # and encoded first: an empty name would build '/v2/snaps/' (a generic 404), and a name with
    # a path separator or dot segment would steer the request to a different endpoint.
    @pytest.mark.parametrize('func', _PATH_FUNCTIONS, ids=lambda f: f.__name__)
    @pytest.mark.parametrize('snap', ['', '.', '..', 'hello-world/conf'])
    def test_invalid_name_raises_value_error_without_request(
        self, mock_client: MockClient, func: Any, snap: str
    ):
        with pytest.raises(ValueError):
            func(snap)
        mock_client.get.assert_not_called()
        mock_client.post.assert_not_called()

    @pytest.mark.parametrize('snap', ['', '.', '..', 'hello-world/conf'])
    def test_hold_invalid_name_raises_value_error_without_request(
        self, mock_client: MockClient, monkeypatch: pytest.MonkeyPatch, snap: str
    ):
        # hold() probes info() before posting; the name is validated before either request.
        info = MagicMock()
        monkeypatch.setattr(_snapd, 'info', info)
        with pytest.raises(ValueError):
            _snapd.hold(snap)
        info.assert_not_called()
        mock_client.post.assert_not_called()

    def test_install_validates_name_before_building_body(self, mock_client: MockClient):
        with pytest.raises(ValueError, match='must not be empty'):
            _snapd.install('', channel='edge', revision=5)

    def test_name_is_percent_encoded(self, mock_client: MockClient):
        mock_client.get.return_value = {**_MINIMAL_INFO_DICT, 'name': 'hello world'}
        _snapd.info('hello world')
        mock_client.get.assert_called_once_with('/v2/snaps/hello%20world')
