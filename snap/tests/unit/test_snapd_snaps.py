# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import pytest

from charmlibs.snap import _snapd_snaps as _snapd
from charmlibs.snap._errors import (
    APIError,
    ChannelNotAvailableError,
    Error,
    NotFoundError,
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


class TestInstalledInfoFromDict:
    def test_basic_fields(self):
        info = _snapd.InstalledInfo._from_dict(_MINIMAL_INFO_DICT)
        assert info.name == 'hello-world'
        assert info.version == '6.4'
        assert info.tracking == 'latest/stable'
        assert info.revision == '29'
        assert info.classic is False
        assert info.hold is None

    def test_local_revision(self):
        info = _snapd.InstalledInfo._from_dict({**_MINIMAL_INFO_DICT, 'revision': 'x1'})
        assert info.revision == 'x1'

    def test_tracking_is_not_the_revision_source_channel(self):
        # 'channel' is the channel the installed revision came from, which can differ from the
        # channel the snap tracks -- installing a revision without a channel tracks
        # latest/stable but sources the revision from wherever it's available.
        info = _snapd.InstalledInfo._from_dict({
            **_MINIMAL_INFO_DICT,
            'channel': 'edge',
            'tracking-channel': 'latest/stable',
        })
        assert info.tracking == 'latest/stable'

    def test_tracking_empty_when_field_absent(self):
        # A snap installed from a local file tracks no channel: snapd omits the field entirely.
        info_dict = {k: v for k, v in _MINIMAL_INFO_DICT.items() if k != 'tracking-channel'}
        info = _snapd.InstalledInfo._from_dict({**info_dict, 'channel': ''})
        assert info.tracking == ''

    @pytest.mark.parametrize('confinement', ['strict', 'devmode'])
    def test_non_classic_confinement(self, confinement: str):
        info = _snapd.InstalledInfo._from_dict({**_MINIMAL_INFO_DICT, 'confinement': confinement})
        assert info.classic is False

    def test_classic_confinement(self):
        info = _snapd.InstalledInfo._from_dict({**_MINIMAL_INFO_DICT, 'confinement': 'classic'})
        assert info.classic is True

    def test_hold_present(self):
        info = _snapd.InstalledInfo._from_dict(result_of('snap_info_hello_world_held.json'))
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
        info = _snapd.InstalledInfo._from_dict(info_dict)
        assert info.name == 'hello-world'


class TestListOne:
    def test_list_one_installed(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        info = _snapd.list_one('hello-world')
        assert info.name == 'hello-world'
        assert info.revision == '29'
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    def test_list_one_classic(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_kube_proxy.json')
        info = _snapd.list_one('kube-proxy')
        assert info.classic is True

    def test_list_one_with_hold(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world_held.json')
        info = _snapd.list_one('hello-world')
        assert info.hold is not None

    def test_list_one_missing_raises(self, mock_client: MockClient):
        mock_client.get.side_effect = _make_snap_not_found()
        with pytest.raises(NotFoundError):
            _snapd.list_one('hello-world')

    def test_list_one_other_error_propagates(self, mock_client: MockClient):
        mock_client.get.side_effect = Error(
            'internal error',
            kind='internal-error',
            value='',
            status_code=500,
            status='Internal Server Error',
        )
        with pytest.raises(Error):
            _snapd.list_one('hello-world')


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
        # snapd answers a remove of an absent snap with the 'snap-not-installed' kind, which the
        # client maps to NotFoundError along with every other way snapd says "it isn't there".
        mock_client.post.side_effect = NotFoundError('', kind='snap-not-installed', value='')
        assert _snapd.remove('hello-world', purge=purge) is False

    def test_remove_other_error_propagates(self, mock_client: MockClient):
        mock_client.post.side_effect = APIError('boom', kind='some-other-kind', value='')
        with pytest.raises(APIError):
            _snapd.remove('hello-world')


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

    def test_refresh_success_is_not_probed(self, mock_client: MockClient):
        _snapd.refresh('hello-world')
        mock_client.get.assert_not_called()

    def test_refresh_no_updates_is_not_probed(self, mock_client: MockClient):
        # The no-updates path is handled before the probe, so it costs no extra request.
        mock_client.post.side_effect = _NoUpdatesAvailableError(
            '', kind='snap-no-update-available', value=''
        )
        assert _snapd.refresh('hello-world') is False
        mock_client.get.assert_not_called()


class TestRefreshNotInstalled:
    # snapd answers a refresh of an absent snap with an error carrying no 'kind', so there's
    # nothing in the response to key off: refresh probes /v2/snaps/{snap} to tell an absent snap
    # apart from any other failure, and raises NotFoundError as the rest of the library does.
    # Built fresh per call: raising an exception mutates its __context__, so a shared instance
    # would leak chaining state between tests.
    @staticmethod
    def _kindless() -> APIError:
        return APIError(
            'cannot refresh "hello-world": snap "hello-world" is not installed',
            kind='',
            value='',
            status_code=400,
        )

    @staticmethod
    def _snap_not_found() -> NotFoundError:
        return NotFoundError('snap not installed', kind='snap-not-found', value='hello-world')

    def test_absent_snap_raises_not_found(self, mock_client: MockClient):
        mock_client.post.side_effect = self._kindless()
        mock_client.get.side_effect = self._snap_not_found()
        with pytest.raises(NotFoundError) as ctx:
            _snapd.refresh('hello-world')
        # snapd's own probe error is raised unchanged: terse message, snap name in value.
        assert ctx.value.kind == 'snap-not-found'
        assert ctx.value.value == 'hello-world'
        assert str(ctx.value) == 'snap not installed (hello-world)'
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    def test_absent_snap_does_not_chain_the_kindless_error(self, mock_client: MockClient):
        # The unclassifiable error snapd sent is suppressed, so the user sees one traceback.
        mock_client.post.side_effect = self._kindless()
        mock_client.get.side_effect = self._snap_not_found()
        with pytest.raises(NotFoundError) as ctx:
            _snapd.refresh('hello-world')
        assert ctx.value.__cause__ is None
        assert ctx.value.__suppress_context__

    def test_installed_snap_reraises_the_original_error(self, mock_client: MockClient):
        # The probe finds the snap, so the failure was something else and snapd's error stands.
        original = self._kindless()
        mock_client.post.side_effect = original
        mock_client.get.return_value = _MINIMAL_INFO_DICT
        with pytest.raises(APIError) as ctx:
            _snapd.refresh('hello-world')
        assert ctx.value is original

    def test_store_sense_not_found_is_reraised_unchanged(self, mock_client: MockClient):
        # The case the probe must not get wrong: refreshing an installed snap that the store no
        # longer offers is itself a NotFoundError, with the store's 'snap not found' message.
        # Since the probe's own error is also a NotFoundError, a probe that raised
        # unconditionally would silently swap the store's error for a "not installed" one that
        # is untrue. It doesn't: the probe finds the snap, so snapd's error is re-raised as is.
        # snapd's path to this is pinned by its own daemon/errors_test.go -- a single-snap
        # SnapActionError{Refresh: ErrSnapNotFound} unwraps to a 404 'snap-not-found'.
        original = NotFoundError(
            'snap not found', kind='snap-not-found', value='hello-world', status_code=404
        )
        mock_client.post.side_effect = original
        mock_client.get.return_value = _MINIMAL_INFO_DICT
        with pytest.raises(NotFoundError) as ctx:
            _snapd.refresh('hello-world')
        assert ctx.value is original
        assert ctx.value.message == 'snap not found'  # Not the probe's 'snap not installed'.

    def test_typed_errors_are_reraised_unchanged(self, mock_client: MockClient):
        # A refresh failure snapd does classify keeps its own type once the probe finds the snap.
        original = ChannelNotAvailableError(
            'no snap revision on specified channel',
            kind='snap-channel-not-available',
            value='',
        )
        mock_client.post.side_effect = original
        mock_client.get.return_value = _MINIMAL_INFO_DICT
        with pytest.raises(ChannelNotAvailableError) as ctx:
            _snapd.refresh('hello-world', channel='no-such-channel')
        assert ctx.value is original


class TestHold:
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

    def test_hold_success_is_not_probed(self, mock_client: MockClient):
        # The probe runs on failure only, so a successful hold makes one request, not two.
        _snapd.hold('hello-world')
        mock_client.get.assert_not_called()

    def test_hold_not_installed(self, mock_client: MockClient):
        # As for refresh, snapd's error for holding an absent snap carries no 'kind', so hold
        # probes /v2/snaps/{snap} and raises snapd's own NotFoundError from that probe.
        mock_client.post.side_effect = APIError(
            'cannot hold "hello-world": snap "hello-world" is not installed',
            kind='',
            value='',
            status_code=400,
        )
        mock_client.get.side_effect = NotFoundError(
            'snap not installed', kind='snap-not-found', value='hello-world'
        )
        with pytest.raises(NotFoundError) as ctx:
            _snapd.hold('hello-world')
        assert str(ctx.value) == 'snap not installed (hello-world)'
        assert ctx.value.__suppress_context__
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    def test_hold_installed_reraises_the_original_error(self, mock_client: MockClient):
        original = APIError('cannot hold', kind='', value='', status_code=400)
        mock_client.post.side_effect = original
        mock_client.get.return_value = _MINIMAL_INFO_DICT
        with pytest.raises(APIError) as ctx:
            _snapd.hold('hello-world')
        assert ctx.value is original


class TestUnhold:
    def test_unhold(self, mock_client: MockClient):
        _snapd.unhold('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'unhold'}
        )


_PATH_FUNCTIONS = [
    _snapd.list_one,
    _snapd.install,
    _snapd.remove,
    _snapd.refresh,
    _snapd.hold,
    _snapd.unhold,
]


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

    def test_install_validates_name_before_building_body(self, mock_client: MockClient):
        with pytest.raises(ValueError, match='must not be empty'):
            _snapd.install('', channel='edge', revision=5)

    def test_name_is_percent_encoded(self, mock_client: MockClient):
        mock_client.get.return_value = {**_MINIMAL_INFO_DICT, 'name': 'hello world'}
        _snapd.list_one('hello world')
        mock_client.get.assert_called_once_with('/v2/snaps/hello%20world')
