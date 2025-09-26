# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime
import io
import json
import pathlib
import subprocess
import time
import typing
import unittest
from subprocess import CalledProcessError
from typing import Any
from unittest.mock import ANY, MagicMock, mock_open, patch

import pytest

import fake_snapd
from charmlibs import snap
from charmlibs.snap import _snap

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

patch('charmlibs.snap._snap._cache_init', lambda x: x).start()  # type: ignore

snap_information_response = json.loads(
    (pathlib.Path(__file__).parent / 'snap_information_response.json').read_text()
)
installed_snaps_response = json.loads(
    (pathlib.Path(__file__).parent / 'installed_snaps_response.json').read_text()
)
installed_snap_apps_response = {
    'type': 'sync',
    'result': [
        {
            'snap': 'juju',
            'name': 'fetch-oci',
            'daemon': 'oneshot',
            'daemon-scope': 'system',
            'enabled': True,
        },
    ],
}


class SnapCacheTester(snap.SnapCache):
    def __init__(self):
        # Fake out __init__ so we can test methods individually
        self._snap_map = {}
        self._snap_client = MagicMock()


class TestSnapCache(unittest.TestCase):
    @patch.object(snap.SnapCache, 'snapd_installed', new=False)
    def test_error_on_not_snapd_installed(self):
        with pytest.raises(snap.SnapError):
            snap.SnapCache()

    @patch(
        'charmlibs.snap._snap.subprocess.check_output',
        return_value=0,
    )
    @patch.object(snap, 'SnapCache', new=SnapCacheTester)
    def test_new_snap_cache_on_first_decorated(self, _mock_check_output: MagicMock):
        """Test that the snap cache is created when a decorated function is called.

        add, remove and ensure are decorated with cache_init, which initialises a new cache
        when these functions are called if there isn't one yet
        """

        class CachePlaceholder:
            cache = None

            def __getitem__(self, name: str) -> snap.Snap:
                return self.cache[name]  # pyright: ignore

        with patch.object(_snap, '_Cache', new=CachePlaceholder()):
            assert _snap._Cache.cache is None
            snap.add(snap_names='curl')
            assert isinstance(_snap._Cache.cache, _snap.SnapCache)

        with patch.object(_snap, '_Cache', new=CachePlaceholder()):
            assert _snap._Cache.cache is None
            snap.remove(snap_names='curl')
            assert isinstance(_snap._Cache.cache, _snap.SnapCache)

        with patch.object(_snap, '_Cache', new=CachePlaceholder()):
            assert _snap._Cache.cache is None
            snap.ensure(snap_names='curl', state='latest')
            assert isinstance(_snap._Cache.cache, _snap.SnapCache)

    @patch('builtins.open', new_callable=mock_open, read_data='foo\nbar\n  \n')
    @patch('os.path.isfile')
    def test_can_load_snap_cache(self, mock_exists: MagicMock, m: MagicMock):
        m.return_value.__iter__ = lambda self: self  # type: ignore
        m.return_value.__next__ = lambda self: next(iter(self.readline, ''))  # type: ignore
        mock_exists.return_value = True
        s = SnapCacheTester()
        s._load_available_snaps()
        assert 'foo' in s._snap_map
        assert len(s._snap_map) == 2

    @patch('os.path.isfile', return_value=False)
    def test_no_load_if_catalog_not_populated(self, mock_isfile: MagicMock):
        s = SnapCacheTester()
        s._load_available_snaps()
        assert not s._snap_map

    @patch('builtins.open', new_callable=mock_open, read_data='curl\n')
    @patch('os.path.isfile')
    def test_can_lazy_load_snap_info(self, mock_exists: MagicMock, m: MagicMock):
        m.return_value.__iter__ = lambda self: self  # type: ignore
        m.return_value.__next__ = lambda self: next(iter(self.readline, ''))  # type: ignore
        mock_exists.return_value = True
        s = SnapCacheTester()
        s._snap_client.get_snap_information.return_value = snap_information_response['result'][0]
        s._load_available_snaps()
        assert 'curl' in s._snap_map

        result = s['curl']
        assert result.name == 'curl'
        assert result.state == snap.SnapState.Available
        assert result.channel == 'stable'
        assert result.confinement == 'strict'
        assert result.revision == '233'
        assert result.version == '7.78.0'

    @patch('os.path.isfile')
    def test_can_load_installed_snap_info(self, mock_exists: MagicMock):
        mock_exists.return_value = True
        s = SnapCacheTester()
        s._snap_client.get_installed_snaps.return_value = installed_snaps_response['result']

        s._load_installed_snaps()

        assert len(s) == 2
        assert 'charmcraft' in s
        assert list(s) == [s['charmcraft'], s['core']]  # test SnapCache.__iter__

        assert s['charmcraft'].name == 'charmcraft'
        assert s['charmcraft'].state == snap.SnapState.Latest
        assert s['charmcraft'].channel == 'latest/stable'
        assert s['charmcraft'].confinement == 'classic'
        assert s['charmcraft'].revision == '603'

    @patch('os.path.isfile')
    def test_raises_error_if_snap_not_running(self, mock_exists: MagicMock):
        mock_exists.return_value = False
        s = SnapCacheTester()
        s._snap_client.get_installed_snaps.side_effect = snap.SnapAPIError(
            {}, 400, 'error', 'snapd is not running'
        )
        with pytest.raises(snap.SnapAPIError) as ctx:
            s._load_installed_snaps()
        repr(ctx.value)  # ensure custom __repr__ doesn't error
        assert 'SnapAPIError' in ctx.value.name
        assert 'snapd is not running' in ctx.value.message

    def test_can_compare_snap_equality(self):
        foo1 = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic', version='v42')
        foo2 = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic')
        assert foo1 == foo2

    def test_can_compare_snap_inequality(self):
        foo1 = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic', version='v42')
        foo2 = snap.Snap('foo', snap.SnapState.Present, 'stable', '2', 'classic', version='v42')
        assert foo1 != foo2

    def test_snap_magic_methods(self):
        foo = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic')
        assert hash(foo) == hash((foo._name, foo._revision))
        str(foo)  # ensure custom __str__ doesn't error
        repr(foo)  # ensure custom __repr__ doesn't error

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_can_run_snap_commands(self, mock_subprocess: MagicMock):
        mock_subprocess.return_value = 0
        foo = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic')
        assert foo.present
        foo.state = snap.SnapState.Present
        mock_subprocess.assert_not_called()

        foo.ensure(snap.SnapState.Absent)
        mock_subprocess.assert_called_with(
            ['snap', 'remove', 'foo'], text=True, stderr=subprocess.PIPE
        )

        foo.ensure(snap.SnapState.Latest, classic=True, channel='latest/edge')

        mock_subprocess.assert_called_with(
            [
                'snap',
                'install',
                'foo',
                '--classic',
                '--channel="latest/edge"',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert foo.latest

        foo.state = snap.SnapState.Absent
        mock_subprocess.assert_called_with(
            ['snap', 'remove', 'foo'], text=True, stderr=subprocess.PIPE
        )

        foo.ensure(snap.SnapState.Latest, revision=123)
        mock_subprocess.assert_called_with(
            ['snap', 'install', 'foo', '--classic', '--revision="123"'],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_refresh_revision_devmode_cohort_args(self, mock_subprocess: MagicMock):
        """Test that ensure and _refresh succeed and call the correct snap commands."""
        foo = snap.Snap(
            name='foo',
            state=snap.SnapState.Present,
            channel='stable',
            revision='1',
            confinement='devmode',
            apps=None,
            cohort='A',
        )
        foo.ensure(snap.SnapState.Latest, revision='2', devmode=True)
        mock_subprocess.assert_called_with(
            [
                'snap',
                'refresh',
                'foo',
                '--revision="2"',
                '--devmode',
                '--cohort="A"',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )

        foo._refresh(leave_cohort=True)
        mock_subprocess.assert_called_with(
            [
                'snap',
                'refresh',
                'foo',
                '--leave-cohort',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert not foo._cohort

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_no_subprocess_when_not_installed(self, mock_subprocess: MagicMock):
        """Don't call out to snap when ensuring an uninstalled state when not installed."""
        foo = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic')
        not_installed_states = (snap.SnapState.Absent, snap.SnapState.Available)
        for _state in not_installed_states:
            foo._state = _state
            for state in not_installed_states:
                foo.ensure(state)
                mock_subprocess.assert_not_called()

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_can_run_snap_commands_devmode(self, mock_check_output: MagicMock):
        mock_check_output.return_value = 0
        foo = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'devmode')
        assert foo.present

        foo.ensure(snap.SnapState.Absent)
        mock_check_output.assert_called_with(
            ['snap', 'remove', 'foo'], text=True, stderr=subprocess.PIPE
        )

        foo.ensure(snap.SnapState.Latest, devmode=True, channel='latest/edge')

        mock_check_output.assert_called_with(
            [
                'snap',
                'install',
                'foo',
                '--devmode',
                '--channel="latest/edge"',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert foo.latest

        foo.state = snap.SnapState.Absent
        mock_check_output.assert_called_with(
            ['snap', 'remove', 'foo'], text=True, stderr=subprocess.PIPE
        )

        foo.ensure(snap.SnapState.Latest, revision='123')
        mock_check_output.assert_called_with(
            ['snap', 'install', 'foo', '--devmode', '--revision="123"'],
            text=True,
            stderr=subprocess.PIPE,
        )

        with pytest.raises(ValueError):  # devmode and classic are mutually exclusive
            foo.ensure(snap.SnapState.Latest, devmode=True, classic=True)

    @patch('charmlibs.snap._snap.subprocess.run')
    def test_can_run_snap_daemon_commands(self, mock_subprocess: MagicMock):
        mock_subprocess.return_value = MagicMock()
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')

        foo.start(['bar', 'baz'], enable=True)
        mock_subprocess.assert_called_with(
            ['snap', 'start', '--enable', 'foo.bar', 'foo.baz'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.stop(['bar'])
        mock_subprocess.assert_called_with(
            ['snap', 'stop', 'foo.bar'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.stop()
        mock_subprocess.assert_called_with(
            ['snap', 'stop', 'foo'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.logs()
        mock_subprocess.assert_called_with(
            ['snap', 'logs', '-n=10', 'foo'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.logs(services=['bar', 'baz'], num_lines=0)  # falsey num_lines is ignored
        mock_subprocess.assert_called_with(
            ['snap', 'logs', 'foo.bar', 'foo.baz'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.restart()
        mock_subprocess.assert_called_with(
            ['snap', 'restart', 'foo'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.restart(['bar', 'baz'], reload=True)
        mock_subprocess.assert_called_with(
            ['snap', 'restart', '--reload', 'foo.bar', 'foo.baz'],
            text=True,
            check=True,
            capture_output=True,
        )

    @patch(
        'charmlibs.snap._snap.subprocess.run',
        side_effect=CalledProcessError(returncode=1, cmd=''),
    )
    def test_snap_daemon_commands_raise_snap_error(self, mock_subprocess: MagicMock):
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')
        with pytest.raises(snap.SnapError):
            foo.start(['bad', 'arguments'], enable=True)

    @patch('charmlibs.snap._snap.subprocess.run')
    def test_snap_connect(self, mock_subprocess: MagicMock):
        mock_subprocess.return_value = MagicMock()
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')

        foo.connect(plug='bar', slot='baz')
        mock_subprocess.assert_called_with(
            ['snap', 'connect', 'foo:bar', 'baz'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.connect(plug='bar')
        mock_subprocess.assert_called_with(
            ['snap', 'connect', 'foo:bar'],
            text=True,
            check=True,
            capture_output=True,
        )

        foo.connect(plug='bar', service='baz', slot='boo')
        mock_subprocess.assert_called_with(
            ['snap', 'connect', 'foo:bar', 'baz:boo'],
            text=True,
            check=True,
            capture_output=True,
        )

    @patch(
        'charmlibs.snap._snap.subprocess.run',
        side_effect=CalledProcessError(returncode=1, cmd=''),
    )
    def test_snap_connect_raises_snap_error(self, mock_subprocess: MagicMock):
        """Ensure that a SnapError is raised when Snap.connect is called with bad arguments."""
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')
        with pytest.raises(snap.SnapError):
            foo.connect(plug='bad', slot='argument')

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_snap_hold_timedelta(self, mock_check_output: MagicMock):
        mock_check_output.return_value = 0
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')

        foo.hold(duration=datetime.timedelta(hours=72))
        mock_check_output.assert_called_with(
            [
                'snap',
                'refresh',
                'foo',
                '--hold=259200s',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_snap_hold_forever(self, mock_subprocess: MagicMock):
        mock_subprocess.return_value = 0
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')

        foo.hold()
        mock_subprocess.assert_called_with(
            [
                'snap',
                'refresh',
                'foo',
                '--hold=forever',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_snap_unhold(self, mock_subprocess: MagicMock):
        mock_subprocess.return_value = 0
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')

        foo.unhold()
        mock_subprocess.assert_called_with(
            [
                'snap',
                'refresh',
                'foo',
                '--unhold',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.SnapClient.get_installed_snap_apps')
    def test_apps_property(self, patched: MagicMock):
        s = SnapCacheTester()
        s._snap_client.get_installed_snaps.return_value = installed_snaps_response['result']
        s._load_installed_snaps()

        patched.return_value = installed_snaps_response['result'][0]['apps']
        assert len(s['charmcraft'].apps) == 2
        assert {'snap': 'charmcraft', 'name': 'charmcraft'} in s['charmcraft'].apps

    @patch('charmlibs.snap._snap.SnapClient.get_installed_snap_apps')
    def test_services_property(self, patched: MagicMock):
        s = SnapCacheTester()
        s._snap_client.get_installed_snaps.return_value = installed_snaps_response['result']
        s._load_installed_snaps()

        patched.return_value = installed_snaps_response['result'][0]['apps']
        assert len(s['charmcraft'].services) == 1
        assert s['charmcraft'].services == {
            'foo_service': {
                'daemon': 'simple',
                'enabled': True,
                'active': False,
                'daemon_scope': None,
                'activators': [],
            }
        }


@patch('charmlibs.snap._snap.subprocess.check_output')
@pytest.mark.parametrize(
    'confinement,classic,expected_flag',
    [
        ('classic', False, ['--classic']),
        ('classic', True, ['--classic']),
        ('strict', False, []),
        ('strict', True, ['--classic']),
    ],
)
def test_refresh_classic(
    mock_subprocess: MagicMock, confinement: str, classic: bool, expected_flag: list[str]
):
    """Test that ensure and _refresh add the --classic flag with confinement set to classic."""
    foo = snap.Snap(
        name='foo',
        state=snap.SnapState.Present,
        channel='stable',
        revision='1',
        confinement=confinement,
        apps=None,
        cohort='A',
    )
    foo.ensure(snap.SnapState.Latest, revision='2', classic=classic)
    mock_subprocess.assert_called_with(
        [
            'snap',
            'refresh',
            'foo',
            '--revision="2"',
            *expected_flag,
            '--cohort="A"',
        ],
        text=True,
        stderr=subprocess.PIPE,
    )


class TestSocketClient(unittest.TestCase):
    def test_socket_not_found(self):
        client = snap.SnapClient(socket_path='/does/not/exist')
        with pytest.raises(snap.SnapAPIError) as ctx:
            client.get_installed_snaps()
        assert isinstance(ctx.value, snap.SnapAPIError)

    def test_fake_socket(self):
        shutdown, socket_path = fake_snapd.start_server()

        try:
            client = snap.SnapClient(socket_path)
            with pytest.raises(snap.SnapAPIError) as ctx:
                client.get_installed_snaps()
            assert isinstance(ctx.value, snap.SnapAPIError)
        finally:
            shutdown()

    @patch('builtins.hasattr', return_value=False)
    def test_not_implemented_raised_when_missing_socket_af_unix(self, _: MagicMock):
        """Assert NotImplementedError raised when missing socket.AF_UNIX."""
        s = _snap._UnixSocketConnection('localhost')
        with pytest.raises(NotImplementedError):
            s.connect()  # hasattr(socket, "AF_UNIX") == False

    def test_request_bad_body_raises_snapapierror(self):
        """Assert SnapAPIError raised on SnapClient._request with bad body."""
        shutdown, socket_path = fake_snapd.start_server()
        try:
            client = snap.SnapClient(socket_path)
            body = {'bad': 'body'}
            with patch.object(
                client,
                '_request_raw',
                side_effect=client._request_raw,
            ) as mock_raw:
                with pytest.raises(snap.SnapAPIError):
                    client._request('GET', 'snaps', body=body)
                mock_raw.assert_called_with(
                    'GET',  # method
                    'snaps',  # path
                    None,  # query
                    {'Accept': 'application/json', 'Content-Type': 'application/json'},  # headers
                    json.dumps(body).encode('utf-8'),  # body
                )
        finally:
            shutdown()

    def test_request_raw_missing_headers_raises_snapapierror(self):
        """Assert SnapAPIError raised on SnapClient._request_raw when missing headers."""
        shutdown, socket_path = fake_snapd.start_server()
        try:
            client = snap.SnapClient(socket_path)
            with patch.object(
                _snap.urllib.request, 'Request', side_effect=_snap.urllib.request.Request
            ) as mock_request:
                with pytest.raises(snap.SnapAPIError):
                    client._request_raw('GET', 'snaps')
            assert mock_request.call_args.kwargs['headers'] == {}
        finally:
            shutdown()

    def test_request_raw_bad_response_raises_snapapierror(self):
        """Assert SnapAPIError raised on SnapClient._request_raw when receiving a bad response."""
        shutdown, socket_path = fake_snapd.start_server()
        try:
            client = snap.SnapClient(socket_path)
            with patch.object(_snap.json, 'loads', return_value={}):
                with pytest.raises(snap.SnapAPIError) as ctx:
                    client._request_raw('GET', 'snaps')
            # the return_value was correctly patched in
            assert ctx.value.body == {}
            # response is bad because it's missing expected keys
            assert ctx.value.message == "KeyError - 'result'"
        finally:
            shutdown()

    def test_wait_changes(self):
        change_started = False
        change_finished = False

        def _request_raw(
            method: str,
            path: str,
            query: dict[str, object] | None = None,
            headers: dict[str, object] | None = None,
            data: bytes | None = None,
        ) -> typing.IO[bytes]:
            nonlocal change_finished
            nonlocal change_started
            if method == 'PUT' and path == 'snaps/test/conf':
                return io.BytesIO(
                    json.dumps({
                        'type': 'async',
                        'status-code': 202,
                        'status': 'Accepted',
                        'result': None,
                        'change': '97',
                    }).encode('utf-8')
                )
            if method == 'GET' and path == 'changes/97' and not change_started:
                change_started = True
                return io.BytesIO(
                    json.dumps({
                        'type': 'sync',
                        'status-code': 200,
                        'status': 'OK',
                        'result': {
                            'id': '97',
                            'kind': 'configure-snap',
                            'summary': 'Change configuration of "test" snap',
                            'status': 'Do',
                            'tasks': [
                                {
                                    'id': '1028',
                                    'kind': 'run-hook',
                                    'summary': 'Run configure hook of "test" snap',
                                    'status': 'Do',
                                    'progress': {'label': '', 'done': 0, 'total': 1},
                                    'spawn-time': '2024-11-28T20:02:47.498399651+00:00',
                                    'data': {'affected-snaps': ['test']},
                                }
                            ],
                            'ready': False,
                            'spawn-time': '2024-11-28T20:02:47.49842583+00:00',
                        },
                    }).encode('utf-8')
                )
            if method == 'GET' and path == 'changes/97' and not change_finished:
                change_finished = True
                return io.BytesIO(
                    json.dumps({
                        'type': 'sync',
                        'status-code': 200,
                        'status': 'OK',
                        'result': {
                            'id': '97',
                            'kind': 'configure-snap',
                            'summary': 'Change configuration of "test" snap',
                            'status': 'Doing',
                            'tasks': [
                                {
                                    'id': '1029',
                                    'kind': 'run-hook',
                                    'summary': 'Run configure hook of "test" snap',
                                    'status': 'Doing',
                                    'progress': {'label': '', 'done': 1, 'total': 1},
                                    'spawn-time': '2024-11-28T20:02:47.498399651+00:00',
                                    'data': {'affected-snaps': ['test']},
                                }
                            ],
                            'ready': False,
                            'spawn-time': '2024-11-28T20:02:47.49842583+00:00',
                        },
                    }).encode('utf-8')
                )
            if method == 'GET' and path == 'changes/97' and change_finished:
                return io.BytesIO(
                    json.dumps({
                        'type': 'sync',
                        'status-code': 200,
                        'status': 'OK',
                        'result': {
                            'id': '98',
                            'kind': 'configure-snap',
                            'summary': 'Change configuration of "test" snap',
                            'status': 'Done',
                            'tasks': [
                                {
                                    'id': '1030',
                                    'kind': 'run-hook',
                                    'summary': 'Run configure hook of "test" snap',
                                    'status': 'Done',
                                    'progress': {'label': '', 'done': 1, 'total': 1},
                                    'spawn-time': '2024-11-28T20:06:41.415929854+00:00',
                                    'ready-time': '2024-11-28T20:06:41.797437537+00:00',
                                    'data': {'affected-snaps': ['test']},
                                }
                            ],
                            'ready': True,
                            'spawn-time': '2024-11-28T20:06:41.415955681+00:00',
                            'ready-time': '2024-11-28T20:06:41.797440022+00:00',
                        },
                    }).encode('utf-8')
                )
            raise RuntimeError('unknown request')

        client = snap.SnapClient()
        with patch.object(client, '_request_raw', _request_raw), patch.object(time, 'sleep'):
            client._put_snap_conf('test', {'foo': 'bar'})

    def test_wait_failed(self):
        def _request_raw(
            method: str,
            path: str,
            query: dict[str, object] | None = None,
            headers: dict[str, object] | None = None,
            data: bytes | None = None,
        ) -> typing.IO[bytes]:
            if method == 'PUT' and path == 'snaps/test/conf':
                return io.BytesIO(
                    json.dumps({
                        'type': 'async',
                        'status-code': 202,
                        'status': 'Accepted',
                        'result': None,
                        'change': '97',
                    }).encode('utf-8')
                )
            if method == 'GET' and path == 'changes/97':
                return io.BytesIO(
                    json.dumps({
                        'type': 'sync',
                        'status-code': 200,
                        'status': 'OK',
                        'result': {
                            'id': '97',
                            'kind': 'configure-snap',
                            'summary': 'Change configuration of "test" snap',
                            'status': 'Error',
                            'ready': False,
                            'spawn-time': '2024-11-28T20:02:47.49842583+00:00',
                        },
                    }).encode('utf-8')
                )
            raise RuntimeError('unknown request')

        client = snap.SnapClient()
        with patch.object(client, '_request_raw', _request_raw), patch.object(time, 'sleep'):
            with pytest.raises(snap.SnapError):
                client._put_snap_conf('test', {'foo': 'bar'})


class TestSnapBareMethods(unittest.TestCase):
    @patch('builtins.open', new_callable=mock_open, read_data='curl\n')
    @patch('os.path.isfile')
    def setUp(self, mock_exists: MagicMock, m: MagicMock):
        m.return_value.__iter__ = lambda self: self  # type: ignore
        m.return_value.__next__ = lambda self: next(iter(self.readline, ''))  # type: ignore
        mock_exists.return_value = True
        _snap._Cache.cache = SnapCacheTester()
        _snap._Cache.cache._snap_client.get_installed_snaps.return_value = (
            installed_snaps_response['result']
        )
        _snap._Cache.cache._snap_client.get_snap_information.return_value = (
            snap_information_response['result'][0]
        )
        _snap._Cache.cache._load_installed_snaps()
        _snap._Cache.cache._load_available_snaps()

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_can_run_bare_changes(self, mock_subprocess: MagicMock):
        mock_subprocess.return_value = 0
        foo = snap.add('curl', classic=True, channel='latest')
        mock_subprocess.assert_called_with(
            ['snap', 'install', 'curl', '--classic', '--channel="latest"'],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert foo.present
        snap.add('curl', state='latest')  # cover string conversion path
        mock_subprocess.assert_called_with(
            ['snap', 'refresh', 'curl', '--channel="latest"', '--classic'],
            text=True,
            stderr=subprocess.PIPE,
        )
        with pytest.raises(TypeError):  # cover error path
            snap.add(snap_names=[])

        bar = snap.remove('curl')
        mock_subprocess.assert_called_with(
            ['snap', 'remove', 'curl'], text=True, stderr=subprocess.PIPE
        )
        assert not bar.present
        with pytest.raises(TypeError):  # cover error path
            snap.remove(snap_names=[])

        baz = snap.add('curl', classic=True, revision=123)
        mock_subprocess.assert_called_with(
            ['snap', 'install', 'curl', '--classic', '--revision="123"'],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert baz.present

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_cohort(self, mock_check_output: MagicMock):
        snap.add('curl', channel='latest', cohort='+')
        mock_check_output.assert_called_with(
            [
                'snap',
                'install',
                'curl',
                '--channel="latest"',
                '--cohort="+"',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )

        snap.ensure('curl', 'latest', classic=True, channel='latest/beta', cohort='+')
        mock_check_output.assert_called_with(
            [
                'snap',
                'refresh',
                'curl',
                '--channel="latest/beta"',
                '--classic',
                '--cohort="+"',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_revision_doesnt_refresh(self, mock_check_output: MagicMock):
        snap.add('curl', revision='233', cohort='+')
        mock_check_output.assert_called_with(
            [
                'snap',
                'install',
                'curl',
                '--revision="233"',
                '--cohort="+"',
            ],
            text=True,
            stderr=subprocess.PIPE,
        )

        mock_check_output.reset_mock()
        # Ensure that calling refresh with the same revision doesn't subprocess out.
        snap.ensure('curl', 'latest', classic=True, revision=233, cohort='+')
        mock_check_output.assert_not_called()

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_can_ensure_states(self, mock_subprocess: MagicMock):
        mock_subprocess.return_value = 0
        foo = snap.ensure('curl', 'latest', classic=True, channel='latest/test')
        mock_subprocess.assert_called_with(
            ['snap', 'install', 'curl', '--classic', '--channel="latest/test"'],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert foo.present

        bar = snap.ensure('curl', 'absent')
        mock_subprocess.assert_called_with(
            ['snap', 'remove', 'curl'], text=True, stderr=subprocess.PIPE
        )
        assert not bar.present

        baz = snap.ensure('curl', 'present', classic=True, revision=123)
        mock_subprocess.assert_called_with(
            ['snap', 'install', 'curl', '--classic', '--revision="123"'],
            text=True,
            stderr=subprocess.PIPE,
        )
        assert baz.present

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_raises_snap_error_on_failed_subprocess(self, mock_subprocess: MagicMock):
        def raise_error(cmd: list[str], **kwargs: Any):
            # If we can't find the snap, we should raise a CalledProcessError.
            #
            # We do it artificially so that this test works on systems w/out snapd installed.
            raise CalledProcessError(returncode=1, cmd=cmd)

        mock_subprocess.side_effect = raise_error
        with pytest.raises(snap.SnapError) as ctx:
            snap.add('nothere')
        repr(ctx.value)  # ensure custom __repr__ doesn't error

    def test_raises_snap_error_on_snap_not_found(self):
        """A cache failure will also ultimately result in a SnapError."""

        class NotFoundCache:
            cache = None

            def __getitem__(self, name: str) -> snap.Snap:
                raise snap.SnapNotFoundError()

        with patch.object(_snap, '_Cache', new=NotFoundCache()):
            with pytest.raises(snap.SnapError) as ctx:
                snap.add('nothere')
        repr(ctx.value)  # ensure custom __repr__ doesn't error
        assert 'SnapError' in ctx.value.name
        assert 'Failed to install or refresh snap(s): nothere' in ctx.value.message

    def test_snap_get(self):
        """Test the multiple different ways of calling the Snap.get function.

        Valid ways:
            ("key", typed=False) -> returns a string
            ("key", typed=True) -> returns value parsed from json
            (None, typed=True) -> returns parsed json for all keys
            ("", typed=True) -> returns parsed json for all keys

        An invalid key will raise an error if typed=False, but return None if typed=True.
        """

        def fake_snap(command: str, optargs: Iterable[str] | None) -> str:
            """Snap._snap would normally call subprocess.check_output(["snap", ...], ...).

            Here we only handle the "get" commands generated by Snap.get:
                ["snap", "get", "-d"] -- equivalent to (None, typed=True)
                ["snap", "get", "key"] -- equivalent to ("key", typed=False)
                ["snap", "get", "-d" "key"] -- equivalent to ("key", typed=True)

            Values are returned from the local keys_and_values dict instead of calling out to snap.
            """
            assert command == 'get'
            assert optargs is not None
            optargs = list(optargs)
            if optargs == ['-d']:
                return json.dumps(keys_and_values)
            if len(optargs) == 1:  # [<some-key>]
                key = optargs[0]
                if key in keys_and_values:
                    return str(keys_and_values[key])
                raise snap.SnapError()
            if len(optargs) == 2 and optargs[0] == '-d':  # ["-d", <some-key>]
                key = optargs[1]
                if key in keys_and_values:
                    return json.dumps({key: keys_and_values[key]})
                return json.dumps({})
            raise snap.SnapError('Bad arguments:', command, optargs)

        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')
        foo._snap = MagicMock(side_effect=fake_snap)
        keys_and_values: dict[str, Any] = {
            'key_w_string_value': 'string',
            'key_w_float_value': 4.2,
            'key_w_int_value': 13,
            'key_w_json_value': {'key1': 'string', 'key2': 4.2, 'key3': 13},
        }
        for key, value in keys_and_values.items():
            assert foo.get(key, typed=True) == value
            assert foo.get(key, typed=False) == str(value)
            assert foo.get(key) == str(value)
        assert foo.get(None, typed=True) == keys_and_values
        assert foo.get('', typed=True) == keys_and_values
        assert foo.get('missing_key', typed=True) is None
        with pytest.raises(snap.SnapError):
            foo.get('missing_key', typed=False)
        with pytest.raises(TypeError):
            foo.get(None, typed=False)
        with pytest.raises(TypeError):
            foo.get(None)

    @patch('charmlibs.snap._snap.SnapClient._put_snap_conf')
    def test_snap_set_typed(self, put_snap_conf: MagicMock):
        foo = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic')

        config = {'n': 42, 's': 'string', 'd': {'nested': True}}

        foo.set(config, typed=True)
        put_snap_conf.assert_called_with('foo', {'n': 42, 's': 'string', 'd': {'nested': True}})

    @patch('charmlibs.snap._snap.SnapClient._put_snap_conf')
    def test_snap_set_untyped(self, put_snap_conf: MagicMock):
        foo = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic')

        config = {'n': 42, 's': 'string', 'd': {'nested': True}}

        foo.set(config, typed=False)
        put_snap_conf.assert_called_with(
            'foo', {'n': '42', 's': 'string', 'd': "{'nested': True}"}
        )

    @patch(
        'charmlibs.snap._snap.subprocess.check_output',
        side_effect=lambda *args, **kwargs: '',  # pyright: ignore[reportUnknownLambdaType]
    )
    def test_snap_unset(self, mock_subprocess: MagicMock):
        foo = snap.Snap('foo', snap.SnapState.Present, 'stable', '1', 'classic')
        key: str = 'test_key'
        assert foo.unset(key) == ''
        mock_subprocess.assert_called_with(
            ['snap', 'unset', 'foo', key],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.run')
    def test_system_set(self, mock_subprocess: MagicMock):
        _snap._system_set('refresh.hold', 'foobar')
        mock_subprocess.assert_called_with(
            ['snap', 'set', 'system', 'refresh.hold=foobar'],
            text=True,
            check=True,
            capture_output=True,
        )

    @patch('charmlibs.snap._snap.subprocess.check_call')
    def test_system_set_fail(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = CalledProcessError(1, 'foobar')
        with pytest.raises(snap.SnapError):
            _snap._system_set('refresh.hold', 'foobar')

    def test_hold_refresh_invalid_too_high(self):
        with pytest.raises(ValueError):
            snap.hold_refresh(days=120)

    def test_hold_refresh_invalid_non_int(self):
        with pytest.raises(TypeError):
            snap.hold_refresh(days='foobar')  # type: ignore

    def test_hold_refresh_invalid_non_bool(self):
        with pytest.raises(TypeError):
            snap.hold_refresh(forever='foobar')  # type: ignore

    @patch('charmlibs.snap._snap.subprocess.run')
    def test_hold_refresh_reset(self, mock_subprocess: MagicMock):
        snap.hold_refresh(days=0)
        mock_subprocess.assert_called_with(
            ['snap', 'set', 'system', 'refresh.hold='],
            text=True,
            check=True,
            capture_output=True,
        )

    @patch('charmlibs.snap._snap.subprocess.run')
    def test_hold_refresh_forever(self, mock_subprocess: MagicMock):
        snap.hold_refresh(forever=True)

        mock_subprocess.assert_called_with(
            ['snap', 'set', 'system', 'refresh.hold=forever'],
            text=True,
            check=True,
            capture_output=True,
        )

    @patch('charmlibs.snap._snap.datetime')
    @patch('charmlibs.snap._snap.subprocess.run')
    def test_hold_refresh_valid_days(self, mock_subprocess: MagicMock, mock_datetime: MagicMock):
        # A little too closely-tied to the internals of hold_refresh(), but at least
        # the test runs whatever your local time zone is.
        mock_datetime.now.return_value.astimezone.return_value = datetime.datetime(
            1970, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
        )

        snap.hold_refresh(days=90)

        mock_subprocess.assert_called_with(
            ['snap', 'set', 'system', 'refresh.hold=1970-04-01T00:00:00+00:00'],
            text=True,
            check=True,
            capture_output=True,
        )

    def test_ansi_filter(self):
        assert (
            snap.ansi_filter.sub('', '\x1b[0m\x1b[?25h\x1b[Khello-world-gtk') == 'hello-world-gtk'
        )
        assert snap.ansi_filter.sub('', '\x1b[0m\x1b[?25h\x1b[Kpypi-server') == 'pypi-server'
        assert snap.ansi_filter.sub('', '\x1b[0m\x1b[?25h\x1b[Kparca') == 'parca'

    @patch('charmlibs.snap._snap.subprocess.check_output', return_value='curl XXX installed')
    def test_install_local(self, mock_subprocess: MagicMock):
        snap.install_local('./curl.snap')
        mock_subprocess.assert_called_with(
            ['snap', 'install', './curl.snap'],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output', return_value='curl XXX installed')
    def test_install_local_classic(self, mock_subprocess: MagicMock):
        snap.install_local('./curl.snap', classic=True)
        mock_subprocess.assert_called_with(
            ['snap', 'install', './curl.snap', '--classic'],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output', return_value='curl XXX installed')
    def test_install_local_devmode(self, mock_subprocess: MagicMock):
        snap.install_local('./curl.snap', devmode=True)
        mock_subprocess.assert_called_with(
            ['snap', 'install', './curl.snap', '--devmode'],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output', return_value='curl XXX installed')
    def test_install_local_dangerous(self, mock_subprocess: MagicMock):
        snap.install_local('./curl.snap', dangerous=True)
        mock_subprocess.assert_called_with(
            ['snap', 'install', './curl.snap', '--dangerous'],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output', return_value='curl XXX installed')
    def test_install_local_classic_dangerous(self, mock_subprocess: MagicMock):
        snap.install_local('./curl.snap', classic=True, dangerous=True)
        mock_subprocess.assert_called_with(
            ['snap', 'install', './curl.snap', '--classic', '--dangerous'],
            text=True,
            stderr=subprocess.PIPE,
        )

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_install_local_snap_api_error(self, mock_subprocess: MagicMock):
        """install_local raises a SnapError if cache access raises a SnapAPIError."""

        class APIErrorCache:
            def __getitem__(self, key: object):
                raise snap.SnapAPIError(body={}, code=123, status='status', message='message')

        mock_subprocess.return_value = 'curl XXX installed'
        with patch.object(_snap, 'SnapCache', new=APIErrorCache):
            with pytest.raises(snap.SnapError) as ctx:
                snap.install_local('./curl.snap')
        assert ctx.value.message == 'Failed to find snap curl in Snap cache'

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_install_local_called_process_error(self, mock_subprocess: MagicMock):
        """install_local raises a SnapError if the subprocess raises a CalledProcessError."""
        mock_subprocess.side_effect = CalledProcessError(
            returncode=1, cmd='cmd', output='dummy-output', stderr='dummy-stderr'
        )
        with pytest.raises(snap.SnapError) as ctx:
            snap.install_local('./curl.snap')
        assert './curl.snap' in ctx.value.message
        assert 'dummy-output' in ctx.value.message
        assert 'dummy-stderr' in ctx.value.message

    @patch('charmlibs.snap._snap.subprocess.run')
    def test_alias(self, mock_run: MagicMock):
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')
        foo.alias('bar', 'baz')
        mock_run.assert_called_once_with(
            ['snap', 'alias', 'foo.bar', 'baz'],
            text=True,
            check=True,
            capture_output=True,
        )
        mock_run.reset_mock()

        foo.alias('bar')
        mock_run.assert_called_once_with(
            ['snap', 'alias', 'foo.bar', 'bar'],
            text=True,
            check=True,
            capture_output=True,
        )
        mock_run.reset_mock()

    @patch('charmlibs.snap._snap.subprocess.run')
    def test_alias_raises_snap_error(self, mock_run: MagicMock):
        mock_run.side_effect = CalledProcessError(
            returncode=1, cmd=['snap', 'alias', 'foo.bar', 'baz']
        )
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')
        with pytest.raises(snap.SnapError):
            foo.alias('bar', 'baz')
        mock_run.assert_any_call(
            ['snap', 'alias', 'foo.bar', 'baz'],
            text=True,
            check=True,
            capture_output=True,
        )
        mock_run.reset_mock()

    @patch('charmlibs.snap._snap.subprocess.check_output')
    def test_held(self, mock_subprocess: MagicMock):
        foo = snap.Snap('foo', snap.SnapState.Latest, 'stable', '1', 'classic')
        mock_subprocess.return_value = {}
        assert not foo.held
        mock_subprocess.return_value = {'hold:': "key isn't checked"}
        assert foo.held


@pytest.fixture
def fake_request(monkeypatch: pytest.MonkeyPatch):
    request = MagicMock()
    monkeypatch.setattr('charmlibs.snap.SnapClient._request', request)
    return request


@pytest.fixture
def snap_client():
    return snap.SnapClient(socket_path='/does/not/exist')


def test_get_installed_snaps(snap_client: snap.SnapClient, fake_request: MagicMock):
    fake_request.return_value = installed_snaps_response['result']
    rv = snap_client.get_installed_snaps()
    charmcraft = next(snap for snap in rv if snap['name'] == 'charmcraft')
    assert charmcraft['version'] == '1.2.1'


def test_get_installed_snap_apps(snap_client: snap.SnapClient, fake_request: MagicMock):
    fake_request.return_value = installed_snap_apps_response['result']
    rv = snap_client.get_installed_snap_apps('juju')
    assert rv == [
        {
            'name': 'fetch-oci',
            'snap': 'juju',
            'daemon': 'oneshot',
            'daemon-scope': ANY,
            'enabled': ANY,
        }
    ]


def test_get_snap_information(snap_client: snap.SnapClient, fake_request: MagicMock):
    fake_request.return_value = snap_information_response['result']
    rv = snap_client.get_snap_information('curl')
    assert rv['version'] == '7.78.0'
