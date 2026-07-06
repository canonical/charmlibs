# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import builtins
import json
import logging
import urllib.error
import urllib.request
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import LogCaptureFixture

import charmlibs.snap._errors
from charmlibs.snap import _client
from charmlibs.snap._errors import (
    APIError,
    AppNotFoundError,
    BadResponseError,
    ChangeError,
    ChannelNotAvailableError,
    ConnectionError,  # noqa: A004 (shadowing a Python builtin)
    Error,
    NeedsClassicError,
    NotFoundError,
    OptionNotFoundError,
    TimeoutError,  # noqa: A004 (shadowing a Python builtin)
    _AlreadyInstalledError,
    _NoUpdatesAvailableError,
)
from conftest import FIXTURES_DIR, load_fixture


def _fake_response(
    data: bytes | dict[str, Any] | list[Any],
    status: int = 200,
    reason: str = 'OK',
    url: str = 'http://localhost/v2/snaps/hello-world',
):
    """Build a fake HTTPResponse-like object for mocking _request."""
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
    return SimpleNamespace(read=lambda: data, status=status, reason=reason, url=url)


@pytest.fixture
def mock_raw(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch _request so tests control the raw HTTP response."""
    mocked = MagicMock()
    monkeypatch.setattr(_client, '_request', mocked)
    return mocked


@pytest.fixture
def mock_json(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch _json_request so tests control the JSON request layer."""
    mocked = MagicMock()
    monkeypatch.setattr(_client, '_json_request', mocked)
    return mocked


class TestRequest:
    def test_get(self, mock_json: MagicMock):
        mock_json.return_value = _fake_response({'type': 'sync', 'result': {'foo': 'bar'}})
        result = _client.get('/v2/snaps/lxd/conf', query={'keys': 'integer'})
        assert mock_json.call_args.args[0] == 'GET'
        assert mock_json.call_args.args[1] == '/v2/snaps/lxd/conf'
        assert mock_json.call_args.kwargs['query'] == {'keys': 'integer'}
        assert mock_json.call_args.kwargs.get('body') is None
        assert result == {'foo': 'bar'}

    def test_get_list_result(self, mock_raw: MagicMock):
        # A list result (e.g. /v2/apps) is passed through unchanged.
        mock_raw.return_value = _fake_response({'type': 'sync', 'result': [1, 2, 3]})
        result = _client.get('/v2/apps')
        assert result == [1, 2, 3]

    def test_post(self, mock_json: MagicMock):
        mock_json.return_value = _fake_response({'type': 'sync', 'result': {'foo': 'bar'}})
        result = _client.post('/v2/snaps/hello-world', body={'action': 'install'})
        assert mock_json.call_args.args[0] == 'POST'
        assert mock_json.call_args.args[1] == '/v2/snaps/hello-world'
        assert mock_json.call_args.kwargs['body'] == {'action': 'install'}
        assert result == {'foo': 'bar'}

    def test_post_no_body_sends_no_data(self, mock_json: MagicMock):
        mock_json.return_value = _fake_response({'type': 'sync', 'result': {}})
        _client.post('/v2/snaps/hello-world')
        assert mock_json.call_args.kwargs.get('body') is None

    def test_put(self, mock_json: MagicMock):
        mock_json.return_value = _fake_response({'type': 'sync', 'result': {'foo': 'bar'}})
        result = _client.put('/v2/snaps/lxd/conf', body={'mykey': 'myval'})
        assert mock_json.call_args.args[0] == 'PUT'
        assert mock_json.call_args.args[1] == '/v2/snaps/lxd/conf'
        assert mock_json.call_args.kwargs['body'] == {'mykey': 'myval'}
        assert result == {'foo': 'bar'}


class TestErrorResponses:
    @pytest.mark.parametrize(
        ('kind', 'expected_type'),
        [
            ('snap-already-installed', _AlreadyInstalledError),
            ('app-not-found', AppNotFoundError),
            ('option-not-found', OptionNotFoundError),
            ('snap-channel-not-available', ChannelNotAvailableError),
            ('snap-needs-classic', NeedsClassicError),
            ('snap-not-found', NotFoundError),
            ('some-unrecognised-kind', APIError),  # Unknown kinds fall back to the base type.
        ],
    )
    def test_error_kind_maps_to_type(
        self, mock_raw: MagicMock, kind: str, expected_type: type[APIError]
    ):
        mock_raw.return_value = _fake_response({
            'type': 'error',
            'status-code': 400,
            'status': 'Bad Request',
            'result': {'message': 'boom', 'kind': kind, 'value': 'the-value'},
        })
        with pytest.raises(expected_type) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert type(exc_info.value) is expected_type  # Exact type, not a subclass.
        # Fields from the response body are preserved on the exception.
        assert exc_info.value.message == 'boom'
        assert exc_info.value.kind == kind
        assert exc_info.value.value == 'the-value'
        assert exc_info.value._status_code == 400

    def test_error_missing_kind_and_value_use_defaults(self, mock_raw: MagicMock):
        # Real responses may omit 'kind' and 'value' entirely.
        mock_raw.return_value = _fake_response({
            'type': 'error',
            'status-code': 400,
            'status': 'Bad Request',
            'result': {'message': 'boom'},
        })
        with pytest.raises(APIError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert type(exc_info.value) is APIError  # Missing kind falls back to the base type.
        assert exc_info.value.kind == ''
        assert exc_info.value.value == ''

    def test_error_converts_value_to_str(self, mock_raw: MagicMock):
        # snap-channel-not-available returns a rich dict as 'value'.
        value = {'channel': 'garbage', 'snap-name': 'hello-world'}
        mock_raw.return_value = _fake_response({
            'type': 'error',
            'status-code': 404,
            'status': 'Not Found',
            'result': {
                'message': 'no channel',
                'kind': 'snap-channel-not-available',
                'value': value,
            },
        })
        with pytest.raises(ChannelNotAvailableError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert exc_info.value.value == str(value)

    @pytest.mark.parametrize(
        ('response', 'message_fragment'),
        [
            (b'not json at all', 'Invalid JSON'),
            (b'[1, 2, 3]', 'Unexpected response type'),
            ({'status-code': 200, 'result': {}}, 'Missing expected key'),  # No 'type' key.
            ({'type': 'sync', 'status-code': 200}, 'Missing expected key'),  # No 'result' key.
        ],
    )
    def test_malformed_response_raises_bad_response_error(
        self, mock_raw: MagicMock, response: bytes | dict[str, Any], message_fragment: str
    ):
        mock_raw.return_value = _fake_response(response)
        with pytest.raises(BadResponseError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert message_fragment in exc_info.value.message

    def test_request_timeout_raises_snap_timeout_error(self, monkeypatch: pytest.MonkeyPatch):
        # Patch opener.open inside _request to raise TimeoutError, exercising the conversion.
        monkeypatch.setattr(
            urllib.request.OpenerDirector,
            'open',
            MagicMock(side_effect=builtins.TimeoutError('timed out')),
        )
        with pytest.raises(TimeoutError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert exc_info.value.kind == 'charmlibs-snap-request-timeout'
        assert isinstance(exc_info.value, TimeoutError)

    def test_socket_not_found_raises_snap_connection_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        # Point _SOCKET_PATH at a real non-existent path so the real URLError fires.
        monkeypatch.setattr(_client, '_SOCKET_PATH', str(tmp_path / 'does-not-exist'))
        # A missing socket means snapd is absent, so the request fails fast without retrying.
        sleep = MagicMock()
        monkeypatch.setattr(_client.time, 'sleep', sleep)
        with pytest.raises(ConnectionError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert exc_info.value.kind == 'charmlibs-snap-socket-not-found'
        assert isinstance(exc_info.value, ConnectionError)
        sleep.assert_not_called()

    def test_connection_error_retries_then_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(_client, '_CONNECTION_RETRY_BUDGET', 0)
        sleep = MagicMock()
        monkeypatch.setattr(_client.time, 'sleep', sleep)
        monkeypatch.setattr(
            urllib.request.OpenerDirector,
            'open',
            MagicMock(side_effect=urllib.error.URLError('connection refused')),
        )
        with pytest.raises(ConnectionError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert exc_info.value.kind == 'charmlibs-snap-connection-error'
        assert isinstance(exc_info.value, ConnectionError)
        # Budget is 0, so the first failure is past the deadline: no retry sleep.
        sleep.assert_not_called()

    def test_connection_error_retried_until_success(
        self, mock_raw: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        # A transient connection failure on a GET is retried, then the retry succeeds.
        monkeypatch.setattr(_client.time, 'sleep', MagicMock())
        mock_raw.side_effect = [
            ConnectionError(
                'connection refused', kind='charmlibs-snap-connection-error', value=''
            ),
            _fake_response({'type': 'sync', 'result': {'foo': 'bar'}}),
        ]
        assert _client.get('/v2/snaps/hello-world') == {'foo': 'bar'}
        assert mock_raw.call_count == 2


class TestAsyncChange:
    def test_async_doing_then_done(self, mock_raw: MagicMock):
        # Async POST polls /v2/changes/{id}: Doing keeps polling, Done returns the data field.
        doing = {'type': 'sync', 'result': {'id': '42', 'status': 'Doing', 'ready': False}}
        done = {
            'type': 'sync',
            'result': {'id': '42', 'status': 'Done', 'ready': True, 'data': {'foo': 'bar'}},
        }
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            _fake_response(doing),
            _fake_response(done),
        ]
        result = _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        assert mock_raw.call_count == 3
        poll_call = mock_raw.call_args_list[1]
        assert poll_call.args[0] == 'GET'
        assert poll_call.args[1] == '/v2/changes/42'
        assert result == {'foo': 'bar'}

    def test_async_error_raises_change_error(self, mock_raw: MagicMock):
        error = {
            'type': 'sync',
            'result': {'id': '42', 'status': 'Error', 'ready': True, 'err': 'install failed'},
        }
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            _fake_response(error),
        ]
        with pytest.raises(ChangeError) as exc_info:
            _client.post('/v2/aliases', body={'action': 'alias'})
        assert exc_info.value.kind == 'charmlibs-snap-change-error'
        assert exc_info.value.message == 'install failed'  # Taken from the 'err' field.
        assert exc_info.value.value == '42'  # The change id.

    def test_async_wait_status_logs_warning(self, mock_raw: MagicMock, caplog: LogCaptureFixture):
        wait: dict[str, Any] = {
            'type': 'sync',
            'result': {'id': '42', 'status': 'Wait', 'ready': False, 'data': {}},
        }
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            _fake_response(wait),
        ]
        with caplog.at_level(logging.WARNING, logger='charmlibs.snap._client'):
            _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        assert any('Wait' in r.message for r in caplog.records)

    def test_async_poll_non_dict_raises_bad_response(self, mock_raw: MagicMock):
        # The /v2/changes/{id} result is a list, which is invalid for a change.
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            _fake_response({'type': 'sync', 'result': []}),
        ]
        with pytest.raises(BadResponseError) as exc_info:
            _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        assert 'Unexpected response type' in exc_info.value.message

    @pytest.mark.parametrize('status', ['Undo', 'Undoing'])
    def test_async_undo_statuses_continue_polling(self, mock_raw: MagicMock, status: str):
        """Undo and Undoing are non-terminal rollback states; polling should continue."""
        undo = {'type': 'sync', 'result': {'id': '42', 'status': status, 'ready': False}}
        error = {
            'type': 'sync',
            'result': {'id': '42', 'status': 'Error', 'ready': True, 'err': 'boom'},
        }
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            _fake_response(undo),
            _fake_response(error),
        ]
        with pytest.raises(ChangeError):
            _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        # POST + poll returning undo status + poll returning error = 3 calls.
        assert mock_raw.call_count == 3

    def test_async_poll_retries_past_transient_unreachable(
        self, mock_raw: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        """A snapd-unreachable poll (e.g. daemon restart mid-refresh) is retried, not failed."""
        monkeypatch.setattr(_client.time, 'sleep', MagicMock())
        done = {'type': 'sync', 'result': {'id': '42', 'status': 'Done', 'ready': True}}
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            # _request translates urllib errors into ConnectionError; mock that here since
            # the patch replaces _request (below that translation).
            ConnectionError(
                'connection refused', kind='charmlibs-snap-connection-error', value=''
            ),
            _fake_response(done),
        ]
        _client.post('/v2/snaps/hello-world', body={'action': 'hold'})  # Should not raise.
        # POST + failed poll + retried poll returning Done = 3 calls.
        assert mock_raw.call_count == 3

    def test_async_poll_reraises_after_retry_budget(
        self, mock_raw: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        """If snapd stays unreachable past the retry budget, the connection error propagates."""
        monkeypatch.setattr(_client, '_CONNECTION_RETRY_BUDGET', 0)
        monkeypatch.setattr(_client.time, 'sleep', MagicMock())
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            # poll fails past the retry budget (see note above re: ConnectionError).
            ConnectionError(
                'connection refused', kind='charmlibs-snap-connection-error', value=''
            ),
        ]
        with pytest.raises(ConnectionError):
            _client.post('/v2/snaps/hello-world', body={'action': 'hold'})

    def test_async_unknown_status_raises_change_error(self, mock_raw: MagicMock):
        # An unrecognised change status raises ChangeError with the 'unknown' kind.
        unknown = {'type': 'sync', 'result': {'id': '42', 'status': 'Fake', 'ready': False}}
        mock_raw.side_effect = [
            _fake_response({'type': 'async', 'change': '42'}),
            _fake_response(unknown),
        ]
        with pytest.raises(ChangeError) as exc_info:
            _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        assert exc_info.value.kind == 'charmlibs-snap-change-unknown'
        assert 'Fake' in exc_info.value.message


class TestLogsEndpoint:
    def test_logs_returns_list_of_entries(self, mock_raw: MagicMock):
        raw = (FIXTURES_DIR / 'logs_lxd_raw.bin').read_bytes()
        mock_raw.return_value = _fake_response(raw)
        result = _client.get_logs(query={'n': 10, 'names': 'lxd'})
        assert isinstance(result, list)
        assert len(result) > 0
        assert 'timestamp' in result[0]

    def test_logs_error_response_raises(self, mock_raw: MagicMock):
        raw = (FIXTURES_DIR / 'app_not_found_raw.bin').read_bytes()
        mock_raw.return_value = _fake_response(raw)
        with pytest.raises(Error) as exc_info:
            _client.get_logs(query={'n': 10, 'names': 'hello-world'})
        assert exc_info.value.kind == 'app-not-found'

    def test_logs_malformed_response_raises_bad_response_error(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(b'some-bytes', url='http://foo/some-path')
        with pytest.raises(BadResponseError) as exc_info:
            _client.get_logs(query={'n': 10, 'names': 'lxd'})
        assert 'Invalid JSON' in exc_info.value.message
        assert 'some-path' in exc_info.value.message
        assert exc_info.value.value == 'some-bytes'


def test_all_errors_mapped():
    unmapped = {
        # Base classes
        'Error',
        'APIError',
        # Transport errors
        'ConnectionError',
        'TimeoutError',
        # Manually raised errors
        'BadResponseError',
        'ChangeError',
    }
    expected = sorted(
        name
        for name in dir(charmlibs.snap._errors)
        if name.endswith('Error') and name not in unmapped
    )
    actual = sorted(cls.__name__ for cls in _client._ERRORS.values())
    assert actual == expected


# ---------------------------------------------------------------------------
# Tests against real snapd responses captured as fixtures.
#
# These are deliberately kept separate from the synthetic tests above. The
# synthetic tests pin down exactly what the client does with hand-written
# inputs; these check only that the client decodes real-world response bodies
# the same way, without implying the synthetic tests exercise real data.
# ---------------------------------------------------------------------------


class TestRealErrorFixtures:
    @pytest.mark.parametrize(
        ('fixture', 'expected_type'),
        [
            ('snap_already_installed_error.json', _AlreadyInstalledError),
            ('snap_needs_classic_error.json', NeedsClassicError),
            ('snap_channel_not_available_error.json', ChannelNotAvailableError),
            ('app_not_found_error.json', AppNotFoundError),
            ('conf_option_not_found_error.json', OptionNotFoundError),
            ('snap_no_update_available_error.json', _NoUpdatesAvailableError),
            ('interfaces_not_installed_error.json', APIError),  # No 'kind' -> base type.
        ],
    )
    def test_sync_error_fixture_decodes_to_exception(
        self, mock_raw: MagicMock, fixture: str, expected_type: type[APIError]
    ):
        envelope = load_fixture(fixture)
        result = envelope['result']
        mock_raw.return_value = _fake_response(envelope)
        response = _client._json_request('GET', '/fake/path')
        with pytest.raises(expected_type) as exc_info:
            _client._decode(response)
        exc = exc_info.value
        assert type(exc) is expected_type  # Exact type, not a subclass.
        assert exc.message == result['message']
        assert exc.kind == result.get('kind', '')
        assert exc.value == str(result.get('value', ''))
        assert exc._status_code == envelope['status-code']


class TestRealChangeFixtures:
    def test_async_change_completes(self, mock_raw: MagicMock):
        # Async POST -> Doing poll -> Done poll, all from real captured responses.
        done = load_fixture('change_done.json')
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_accepted.json')),
            _fake_response(load_fixture('change_doing.json')),
            _fake_response(done),
        ]
        result = _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        assert mock_raw.call_count == 3
        assert result == done['result']['data']

    @pytest.mark.parametrize('fixture', ['change_error.json', 'change_error_alias_conflict.json'])
    def test_async_change_error(self, mock_raw: MagicMock, fixture: str):
        async_envelope = load_fixture('async_accepted.json')
        change = load_fixture(fixture)['result']
        mock_raw.side_effect = [
            _fake_response(async_envelope),
            _fake_response(load_fixture(fixture)),
        ]
        with pytest.raises(ChangeError) as exc_info:
            _client.post('/v2/aliases', body={'action': 'alias'})
        assert exc_info.value.kind == 'charmlibs-snap-change-error'
        assert exc_info.value.message == change['err']  # Message comes from the 'err' field.
        assert exc_info.value.value == str(async_envelope['change'])  # The polled change id.
