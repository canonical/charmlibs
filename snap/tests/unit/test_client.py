# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest import LogCaptureFixture
    from pytest_mock import MockerFixture

from charmlibs.snap import _client
from charmlibs.snap._errors import (
    SnapAlreadyInstalledError,
    SnapAPIError,
    SnapChangeError,
    SnapError,
    SnapNeedsClassicError,
    SnapNotFoundError,
    SnapOptionNotFoundError,
    SnapTimeoutError,
)
from conftest import FIXTURES_DIR, load_fixture


def _fake_response(
    data: bytes | dict[str, Any] | list[Any], status: int = 200, reason: str = 'OK'
):
    """Build a fake HTTPResponse-like object for mocking _request_raw."""
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
    return SimpleNamespace(read=lambda: data, status=status, reason=reason)


@pytest.fixture
def mock_raw(mocker: MockerFixture) -> MagicMock:
    """Patch _request_raw so tests control the raw HTTP response."""
    return mocker.patch('charmlibs.snap._client._request_raw')


class TestGet:
    def test_get_returns_result(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('snap_info_hello_world.json'))
        result = _client.get('/v2/snaps/hello-world')
        assert isinstance(result, dict)
        assert result['name'] == 'hello-world'

    def test_get_passes_path(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('conf_lxd_all.json'))
        _client.get('/v2/snaps/lxd/conf')
        assert mock_raw.call_args.args[1] == '/v2/snaps/lxd/conf'

    def test_get_passes_method(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('snap_info_hello_world.json'))
        _client.get('/v2/snaps/hello-world')
        assert mock_raw.call_args.args[0] == 'GET'

    def test_get_passes_query(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('conf_lxd_single_key.json'))
        _client.get('/v2/snaps/lxd/conf', query={'keys': 'integer'})
        assert mock_raw.call_args.kwargs['query'] == {'keys': 'integer'}

    def test_get_no_body(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('snap_info_hello_world.json'))
        _client.get('/v2/snaps/hello-world')
        assert mock_raw.call_args.kwargs.get('data') is None


class TestPost:
    def test_post_passes_method(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_already_installed_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapAlreadyInstalledError):
            _client.post('/v2/snaps/hello-world', body={'action': 'install'})
        assert mock_raw.call_args.args[0] == 'POST'

    def test_post_sends_json_body(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_already_installed_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapAlreadyInstalledError):
            _client.post('/v2/snaps/hello-world', body={'action': 'install'})
        sent = mock_raw.call_args.kwargs['data']
        assert json.loads(sent) == {'action': 'install'}

    def test_post_sets_content_type(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_already_installed_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapAlreadyInstalledError):
            _client.post('/v2/snaps/hello-world', body={'action': 'install'})
        headers = mock_raw.call_args.kwargs['headers']
        assert headers['Content-Type'] == 'application/json'

    def test_post_no_body_sends_no_data(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response({
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': {},
        })
        _client.post('/v2/snaps/hello-world')
        assert mock_raw.call_args.kwargs.get('data') is None


class TestPut:
    def test_put_passes_method(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('conf_lxd_all.json'))
        _client.put('/v2/snaps/lxd/conf', body={'key': 'val'})
        assert mock_raw.call_args.args[0] == 'PUT'

    def test_put_sends_json_body(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('conf_lxd_all.json'))
        _client.put('/v2/snaps/lxd/conf', body={'mykey': 'myval'})
        sent = mock_raw.call_args.kwargs['data']
        assert json.loads(sent) == {'mykey': 'myval'}


class TestSyncResponse:
    def test_sync_returns_result_field(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('snap_info_hello_world.json'))
        result = _client.get('/v2/snaps/hello-world')
        assert result == load_fixture('snap_info_hello_world.json')['result']

    def test_sync_list_result(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('services_lxd.json'))
        result = _client.get('/v2/apps')
        assert isinstance(result, list)
        assert len(result) == 3

    def test_sync_dict_result(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('conf_lxd_all.json'))
        result = _client.get('/v2/snaps/lxd/conf')
        assert isinstance(result, dict)

    def test_accept_header_set(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(load_fixture('snap_info_hello_world.json'))
        _client.get('/v2/snaps/hello-world')
        headers = mock_raw.call_args.kwargs['headers']
        assert headers['Accept'] == 'application/json'


class TestErrorResponses:
    def test_snap_already_installed(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_already_installed_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapAlreadyInstalledError) as exc_info:
            _client.post('/v2/snaps/hello-world', body={'action': 'install'})
        assert 'already installed' in str(exc_info.value)

    def test_snap_needs_classic(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_needs_classic_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapNeedsClassicError):
            _client.post('/v2/snaps/just', body={'action': 'install'})

    def test_snap_not_found(self, mock_raw: MagicMock):
        fixture = {
            'type': 'error',
            'status-code': 404,
            'status': 'Not Found',
            'result': {
                'message': 'snap "nope" not found',
                'kind': 'snap-not-found',
                'value': 'nope',
            },
        }
        mock_raw.return_value = _fake_response(fixture, status=404, reason='Not Found')
        with pytest.raises(SnapNotFoundError):
            _client.get('/v2/snaps/nope')

    def test_option_not_found(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('conf_option_not_found_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapOptionNotFoundError):
            _client.get('/v2/snaps/lxd/conf', query={'keys': 'keydoesnotexist01'})

    def test_unknown_error_kind_raises_snap_error(self, mock_raw: MagicMock):
        fixture = {
            'type': 'error',
            'status-code': 500,
            'status': 'Internal Server Error',
            'result': {'message': 'something unexpected', 'kind': 'unknown-kind', 'value': ''},
        }
        mock_raw.return_value = _fake_response(fixture, status=500, reason='Internal Server Error')
        with pytest.raises(SnapError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert type(exc_info.value) is SnapError

    def test_error_preserves_status_code(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_already_installed_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapAlreadyInstalledError) as exc_info:
            _client.post('/v2/snaps/hello-world', body={'action': 'install'})
        assert exc_info.value._status_code == 400

    def test_error_preserves_kind(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_needs_classic_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapNeedsClassicError) as exc_info:
            _client.post('/v2/snaps/just', body={'action': 'install'})
        assert exc_info.value.kind == 'snap-needs-classic'

    def test_error_preserves_value(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(
            load_fixture('snap_already_installed_error.json'), status=400, reason='Bad Request'
        )
        with pytest.raises(SnapAlreadyInstalledError) as exc_info:
            _client.post('/v2/snaps/hello-world', body={'action': 'install'})
        assert exc_info.value.value == 'hello-world'

    def test_invalid_json_raises_snap_api_error(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(b'not json at all', status=200, reason='OK')
        with pytest.raises(SnapAPIError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert 'Invalid JSON' in exc_info.value.message

    def test_missing_type_key_raises_snap_api_error(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response({'status-code': 200, 'result': {}})
        with pytest.raises(SnapAPIError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert 'Missing expected key' in exc_info.value.message

    def test_non_dict_response_raises_snap_api_error(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(b'[1, 2, 3]', status=200, reason='OK')
        with pytest.raises(SnapAPIError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert 'Unexpected response type' in exc_info.value.message

    def test_request_timeout_raises_snap_timeout_error(self, mocker: MockerFixture):
        # Patch opener.open inside _request_raw to raise TimeoutError, exercising the conversion.
        mocker.patch('urllib.request.OpenerDirector.open', side_effect=TimeoutError('timed out'))
        with pytest.raises(SnapTimeoutError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert exc_info.value.kind == 'charmlibs-snap-request-timeout'
        assert isinstance(exc_info.value, TimeoutError)


class TestAsyncChange:
    def test_async_triggers_poll(self, mock_raw: MagicMock):
        done_envelope = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': load_fixture('change_done.json')['result'],
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_hold.json'), status=202, reason='Accepted'),
            _fake_response(done_envelope),
        ]
        _client.post(
            '/v2/snaps/hello-world',
            body={'action': 'hold', 'hold-level': 'general', 'time': 'forever'},
        )
        # First call was the POST, second was the GET /v2/changes/{id}
        assert mock_raw.call_count == 2
        poll_call = mock_raw.call_args_list[1]
        assert poll_call.args[0] == 'GET'
        assert '/v2/changes/' in poll_call.args[1]

    def test_async_doing_then_done(self, mock_raw: MagicMock):
        # Real Doing fixture followed by the Done one — exercises the poll loop
        doing_envelope = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': load_fixture('change_doing.json')['result'],
        }
        done_envelope = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': load_fixture('change_done.json')['result'],
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_hold.json'), status=202, reason='Accepted'),
            _fake_response(doing_envelope),
            _fake_response(done_envelope),
        ]
        result = _client.post(
            '/v2/snaps/hello-world',
            body={'action': 'hold', 'hold-level': 'general', 'time': 'forever'},
        )
        assert mock_raw.call_count == 3
        # Returns the data field from the Done response
        assert result == load_fixture('change_done.json')['result'].get('data', {})

    def test_async_done_returns_data(self, mock_raw: MagicMock):
        done_envelope = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': load_fixture('change_done.json')['result'],
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_hold.json'), status=202, reason='Accepted'),
            _fake_response(done_envelope),
        ]
        result = _client.post(
            '/v2/snaps/hello-world',
            body={'action': 'hold', 'hold-level': 'general', 'time': 'forever'},
        )
        expected_data = load_fixture('change_done.json')['result']['data']
        assert result == expected_data

    def test_async_error_raises_snap_change_error(self, mock_raw: MagicMock):
        error_envelope = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': load_fixture('change_error.json')['result'],
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_error.json'), status=202, reason='Accepted'),
            _fake_response(error_envelope),
        ]
        with pytest.raises(SnapChangeError) as exc_info:
            _client.post(
                '/v2/aliases',
                body={
                    'action': 'alias',
                    'snap': 'hello-world',
                    'app': 'nonexistent',
                    'alias': 'test-alias-error-fixture',
                },
            )
        assert 'nonexistent' in exc_info.value.message

    def test_async_error_message_from_err_field(self, mock_raw: MagicMock):
        error_envelope = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': load_fixture('change_error.json')['result'],
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_error.json'), status=202, reason='Accepted'),
            _fake_response(error_envelope),
        ]
        with pytest.raises(SnapChangeError) as exc_info:
            _client.post(
                '/v2/aliases',
                body={
                    'action': 'alias',
                    'snap': 'hello-world',
                    'app': 'nonexistent',
                    'alias': 'test-alias-error-fixture',
                },
            )
        change_result = load_fixture('change_error.json')['result']
        assert exc_info.value.message == change_result['err']
        assert exc_info.value.value == change_result['id']

    def test_async_wait_status_logs_warning(self, mock_raw: MagicMock, caplog: LogCaptureFixture):
        wait_result: dict[str, Any] = {
            'id': '42',
            'kind': 'install-snap',
            'summary': 'Install snap',
            'status': 'Wait',
            'ready': False,
            'data': {},
        }
        wait_envelope: dict[str, Any] = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': wait_result,
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_hold.json'), status=202, reason='Accepted'),
            _fake_response(wait_envelope),
        ]
        with caplog.at_level(logging.WARNING, logger='charmlibs.snap._client'):
            _client.post(
                '/v2/snaps/hello-world',
                body={'action': 'hold', 'hold-level': 'general', 'time': 'forever'},
            )
        assert any('Wait' in r.message for r in caplog.records)

    def test_async_change_poll_non_dict_raises_snap_api_error(self, mock_raw: MagicMock):
        # /v2/changes/{id} result is a list.
        # This passes _request's dict check but fails in _wait_for_change.
        poll_envelope: dict[str, Any] = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': [],
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_hold.json'), status=202, reason='Accepted'),
            _fake_response(poll_envelope),
        ]
        with pytest.raises(SnapAPIError) as exc_info:
            _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        assert 'Unexpected response type' in exc_info.value.message

    def test_async_timeout_raises(self, mock_raw: MagicMock, mocker: MockerFixture):
        mocker.patch('charmlibs.snap._client._CHANGE_TIMEOUT', 0)
        mocker.patch('charmlibs.snap._client.time.sleep')
        doing_result = {
            'id': '42',
            'kind': 'install-snap',
            'summary': 'Install',
            'status': 'Doing',
            'ready': False,
        }
        doing_envelope = {
            'type': 'sync',
            'status-code': 200,
            'status': 'OK',
            'result': doing_result,
        }
        mock_raw.side_effect = [
            _fake_response(load_fixture('async_hold.json'), status=202, reason='Accepted'),
            _fake_response(doing_envelope),
        ]
        with pytest.raises(SnapTimeoutError) as exc_info:
            _client.post('/v2/snaps/hello-world', body={'action': 'hold'})
        assert exc_info.value.kind == 'charmlibs-snap-change-timeout'
        assert 'snap change' in exc_info.value.message
        assert isinstance(exc_info.value, TimeoutError)


class TestLogsEndpoint:
    def test_logs_returns_list_of_entries(self, mock_raw: MagicMock):
        raw = (FIXTURES_DIR / 'logs_lxd_raw.bin').read_bytes()
        mock_raw.return_value = _fake_response(raw)
        result = _client.get('/v2/logs', query={'n': 10, 'names': 'lxd'})
        assert isinstance(result, list)
        assert len(result) > 0
        assert 'timestamp' in result[0]

    def test_logs_error_response_raises(self, mock_raw: MagicMock):
        raw = (FIXTURES_DIR / 'app_not_found_raw.bin').read_bytes()
        mock_raw.return_value = _fake_response(raw)
        with pytest.raises(SnapError) as exc_info:
            _client.get('/v2/logs', query={'n': 10, 'names': 'hello-world'})
        assert exc_info.value.kind == 'app-not-found'
