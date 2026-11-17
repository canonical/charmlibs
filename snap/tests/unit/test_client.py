# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import builtins
import contextlib
import http.client
import json
import logging
import pathlib
import socket
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from pytest import LogCaptureFixture

import charmlibs.snap._errors
from charmlibs.snap import _client, _client_sockets
from charmlibs.snap._errors import (
    APIError,
    AppNotFoundError,
    BadResponseError,
    ChangeError,
    ChannelNotAvailableError,
    ConnectionError,  # noqa: A004 (shadowing a Python builtin)
    Error,
    NeedsClassicError,
    NotInstalledError,
    OptionNotFoundError,
    SocketNotFoundError,
    TimeoutError,  # noqa: A004 (shadowing a Python builtin)
    _AlreadyInstalledError,
    _NotFoundError,
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
    return SimpleNamespace(
        read=lambda: data, status=status, reason=reason, url=url, close=lambda: None
    )


# A fake snapd on a real unix socket, used by TestSnapdGoingAwayMidRequest below. Each name is
# one connection's worth of behaviour; a server is given one per connection it should accept.
_RECV_SIZE = 4096
# Long enough for the client's request to land in the receive buffer before we close on it.
# Only the 'abort' behaviour waits, and only to make the reset the *unread* kind (see below).
_ABORT_DELAY = 0.2


def _abort(conn: socket.socket) -> None:
    """Reset the connection instead of closing it cleanly, the way an aborting peer does.

    Closing while the peer's data sits unread in the receive buffer makes the kernel send RST
    rather than FIN, so the client gets ECONNRESET -- the errno 104 a live snapd was seen to
    produce when it goes away mid-request. SO_LINGER with a zero timeout forces the same for a
    connection whose request we did read.
    """
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))


def _serve(server: socket.socket, behaviours: tuple[str, ...]) -> None:
    for behaviour in behaviours:
        conn, _ = server.accept()
        with conn:
            if behaviour == 'abort':
                # Never read the request, so closing on it resets the connection. The wait is
                # only to let the request land in the buffer first.
                time.sleep(_ABORT_DELAY)
                continue
            if behaviour == 'reset_mid_body':
                # Answer with headers the client can parse, then reset while it reads the body,
                # so the failure lands in _read rather than _request. Again, don't read.
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n' + b'x' * 10)
                time.sleep(_ABORT_DELAY)
                _abort(conn)
                continue
            conn.recv(_RECV_SIZE)  # Read the request, so the failure is in our answer, not theirs.
            if behaviour == 'close':
                continue  # Close without answering at all.
            if behaviour == 'truncated_body':
                # Promise more body than we send, so read() raises http.client.IncompleteRead.
                conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n{"type": "sync"')
                continue
            if behaviour == 'not_http':
                # Something that isn't snapd on the socket: http.client.BadStatusLine.
                conn.sendall(b'this is not a status line\r\n\r\n')
                continue
            body = json.dumps({'type': 'sync', 'result': {'foo': 'bar'}}).encode()
            conn.sendall(
                b'HTTP/1.1 200 OK\r\nContent-Length: '
                + str(len(body)).encode()
                + b'\r\n\r\n'
                + body
            )


# Each failure a peer can hand us once the request is on the wire: the behaviour that provokes
# it, the raw error urllib lets through, and which of the two places we touch the socket it
# surfaces from -- 'sending' for _request (which covers h.getresponse()), 'reading' for _read.
#
# Both flavours of _client._TRANSPORT_ERRORS arise at both places, which is why both except arms
# need the whole tuple: 'not_http' is the pure-HTTPException case that catching OSError alone
# would miss in _request, and 'reset_mid_body' the pure-OSError case that catching HTTPException
# alone would miss in _read. RemoteDisconnected subclasses ConnectionResetError, so the 'abort'
# expectation holds whether or not the request lands unread in time to make the reset the
# kernel-level kind.
_FAILURES = [
    ('abort', builtins.ConnectionResetError, 'sending'),
    ('close', http.client.RemoteDisconnected, 'sending'),
    ('not_http', http.client.BadStatusLine, 'sending'),
    ('truncated_body', http.client.IncompleteRead, 'reading'),
    ('reset_mid_body', builtins.ConnectionResetError, 'reading'),
]


@contextlib.contextmanager
def _snapd_that(*behaviours: str) -> Iterator[str]:
    """Serve one connection per behaviour on a real unix socket, and yield its path."""
    # pytest's tmp_paths are too long -- a unix socket path has to fit in sockaddr_un (108 bytes).
    with tempfile.TemporaryDirectory() as tmp:
        socket_path = str(pathlib.Path(tmp) / 's')
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Bound and listening before we yield, so the client can't connect before we're ready.
        server.bind(socket_path)
        server.listen(len(behaviours))
        server.settimeout(10)  # Don't hang the suite if the client never connects.
        thread = threading.Thread(target=_serve, args=(server, behaviours), daemon=True)
        thread.start()
        try:
            yield socket_path
        finally:
            thread.join(timeout=10)
            server.close()


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
            ('snap-not-found', _NotFoundError),
            ('snap-not-installed', NotInstalledError),
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
        assert exc_info.value._kind == kind
        assert exc_info.value._value == 'the-value'
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
        assert exc_info.value._kind == ''
        assert exc_info.value._value == ''

    def test_error_keeps_non_string_value(self, mock_raw: MagicMock):
        # snap-channel-not-available returns a rich dict as 'value', which is kept as decoded.
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
        assert exc_info.value._value == value
        # A non-string value isn't appended to str(), which would be unreadable.
        assert str(exc_info.value) == 'no channel'

    @pytest.mark.parametrize(
        ('response', 'message_fragment', 'expected_response'),
        [
            # Undecodable JSON is reported as the text snapd sent, decoded as best we can.
            (b'not json at all', 'Invalid JSON', 'not json at all'),
            # Well-formed JSON of the wrong shape is reported as the decoded value.
            (b'[1, 2, 3]', 'Unexpected response type', [1, 2, 3]),
            (
                {'status-code': 200, 'result': {}},  # No 'type' key.
                'Missing expected key',
                {'status-code': 200, 'result': {}},
            ),
            (
                {'type': 'sync', 'status-code': 200},  # No 'result' key.
                'Missing expected key',
                {'type': 'sync', 'status-code': 200},
            ),
        ],
    )
    def test_malformed_response_raises_bad_response_error(
        self,
        mock_raw: MagicMock,
        response: bytes | dict[str, Any],
        message_fragment: str,
        expected_response: object,
    ):
        mock_raw.return_value = _fake_response(response)
        with pytest.raises(BadResponseError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert message_fragment in exc_info.value.message
        # What snapd sent is kept for the caller to report to the library maintainers.
        assert exc_info.value._response == expected_response

    @pytest.mark.parametrize('status', [200, 400, 404, 500])
    def test_non_redirect_status_is_decoded_from_the_body(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ):
        # Only 3xx is special-cased in _request: 4xx and 5xx bodies carry the error we report.
        body = {'type': 'sync', 'status-code': status, 'result': {'foo': 'bar'}}
        response = _fake_response(body, status=status)
        monkeypatch.setattr(
            urllib.request.OpenerDirector, 'open', MagicMock(return_value=response)
        )
        assert _client.get('/v2/snaps/hello-world') == {'foo': 'bar'}

    def test_redirect_raises_bad_response_error(self, monkeypatch: pytest.MonkeyPatch):
        # snapd's router answers a non-canonical path (e.g. the '/v2/snaps//conf' that an empty
        # snap name used to build) with an empty-bodied 301 to the cleaned path. We don't follow
        # redirects: we report them, rather than failing on the empty body as invalid JSON.
        def getheader(name: str) -> str | None:
            return '/v2/snaps/conf' if name == 'Location' else None

        response = SimpleNamespace(
            read=lambda: b'',
            status=301,
            reason='Moved Permanently',
            url='http://localhost/v2/snaps//conf',
            getheader=getheader,
            close=lambda: None,
        )
        monkeypatch.setattr(
            urllib.request.OpenerDirector, 'open', MagicMock(return_value=response)
        )
        with pytest.raises(BadResponseError) as exc_info:
            _client.get('/v2/snaps//conf')
        assert '/v2/snaps//conf' in exc_info.value.message  # The path we asked for.
        assert '/v2/snaps/conf' in exc_info.value.message  # Where snapd points us.
        assert '301' in exc_info.value.message  # The kind of redirect it is.
        # The 301's body is empty, and the message already says everything there is to say.
        assert exc_info.value._response is None

    def test_request_timeout_raises_snap_timeout_error(self, monkeypatch: pytest.MonkeyPatch):
        # Patch opener.open inside _request to raise TimeoutError, exercising the conversion.
        monkeypatch.setattr(
            urllib.request.OpenerDirector,
            'open',
            MagicMock(side_effect=builtins.TimeoutError('timed out')),
        )
        with pytest.raises(TimeoutError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert 'timed out' in exc_info.value.message
        assert isinstance(exc_info.value, builtins.TimeoutError)

    def test_socket_not_found_raises_socket_not_found_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        # Point _SOCKET_PATH at a real non-existent path so the real URLError fires.
        monkeypatch.setattr(_client, '_SOCKET_PATH', str(tmp_path / 'does-not-exist'))
        # A missing socket means snapd is absent, so the request fails fast without retrying.
        sleep = MagicMock()
        monkeypatch.setattr(_client.time, 'sleep', sleep)
        with pytest.raises(SocketNotFoundError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        assert 'does-not-exist' in exc_info.value.message  # The socket path we looked for.
        # Callers that only care that snapd was unreachable can catch ConnectionError.
        assert isinstance(exc_info.value, ConnectionError)
        sleep.assert_not_called()

    def test_timeout_while_reading_body_raises_snap_timeout_error(self, mock_raw: MagicMock):
        response = _fake_response({'type': 'sync', 'result': {}})
        response.read = MagicMock(side_effect=builtins.TimeoutError('timed out'))
        mock_raw.return_value = response
        with pytest.raises(TimeoutError) as exc_info:
            _client.get('/v2/snaps/hello-world')
        # The failure was reading the body, not making the request.
        assert 'reading snapd response' in exc_info.value.message

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
        assert 'connection refused' in exc_info.value.message  # urllib's reason, passed through.
        # A reachable-but-failing socket isn't the socket-missing case.
        assert not isinstance(exc_info.value, SocketNotFoundError)
        # Budget is 0, so the first failure is past the deadline: no retry sleep.
        sleep.assert_not_called()

    def test_connection_error_retried_until_success(
        self, mock_raw: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        # A transient connection failure on a GET is retried, then the retry succeeds.
        monkeypatch.setattr(_client.time, 'sleep', MagicMock())
        mock_raw.side_effect = [
            ConnectionError('connection refused'),
            _fake_response({'type': 'sync', 'result': {'foo': 'bar'}}),
        ]
        assert _client.get('/v2/snaps/hello-world') == {'foo': 'bar'}
        assert mock_raw.call_count == 2


class TestSnapdGoingAwayMidRequest:
    """Transport failures reproduced against a real unix socket, not a mocked opener.

    urllib only wraps failures from opening the connection and sending the request, in
    AbstractHTTPHandler.do_open. Anything that goes wrong while the peer is *answering* reaches
    us untranslated, which is what the except arms in _request and _read exist for. These tests
    pin down both halves: that urllib really does let each failure through, and that the library
    converts it. The first half is the premise, so it's asserted rather than assumed -- if a
    future Python starts wrapping these, these tests fail and those arms can go.

    See _FAILURES for the cases and why each one is there.
    """

    @pytest.mark.parametrize(('behaviour', 'raw_type', 'stage'), _FAILURES)
    def test_urllib_lets_the_failure_through_untranslated(
        self, behaviour: str, raw_type: type[BaseException], stage: str
    ):
        with _snapd_that(behaviour) as socket_path:
            opener = urllib.request.OpenerDirector()
            opener.add_handler(_client_sockets.UnixSocketHandler(socket_path))
            request = urllib.request.Request('http://localhost/v2/snaps/hello-world')
            with pytest.raises(raw_type) as exc_info:
                # This drives urllib directly, so _read isn't there to close the response.
                with contextlib.closing(opener.open(request, timeout=10)) as response:
                    # Getting this far means urllib parsed a response, so the failure is in the
                    # body.
                    assert stage == 'reading'
                    response.read()
        if stage == 'sending':
            assert not isinstance(exc_info.value, urllib.error.URLError)
        assert isinstance(exc_info.value, _client._TRANSPORT_ERRORS)

    @pytest.mark.parametrize(('behaviour', 'raw_type', 'stage'), _FAILURES)
    def test_the_library_translates_the_failure(
        self,
        behaviour: str,
        raw_type: type[BaseException],
        stage: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Budget 0 so the GET isn't retried: one connection is all the server offers. (A failure
        # while reading the body isn't retried anyway -- that happens after _retry_json_get.)
        monkeypatch.setattr(_client, '_CONNECTION_RETRY_BUDGET', 0)
        monkeypatch.setattr(_client.time, 'sleep', MagicMock())
        with _snapd_that(behaviour) as socket_path:
            monkeypatch.setattr(_client, '_SOCKET_PATH', socket_path)
            with pytest.raises(ConnectionError) as exc_info:
                _client.get('/v2/snaps/hello-world')
        # A raw ConnectionResetError would satisfy pytest.raises above, since the library's
        # ConnectionError subclasses the builtin -- check the failure really was translated.
        assert isinstance(exc_info.value, Error)
        assert 'Connection to snapd lost' in exc_info.value.message
        # The socket existed and accepted us, so this isn't the snapd-not-installed case.
        assert not isinstance(exc_info.value, SocketNotFoundError)
        # The raw error is kept as the cause, so a charm's traceback still shows what broke.
        assert isinstance(exc_info.value.__cause__, raw_type)

    def test_the_failure_is_retried_on_a_get(self, monkeypatch: pytest.MonkeyPatch):
        # Translating these is what puts them in front of the GET retry, and snapd restarting
        # mid-operation -- exactly this failure -- is what that retry exists for.
        monkeypatch.setattr(_client.time, 'sleep', MagicMock())
        with _snapd_that('abort', 'ok') as socket_path:
            monkeypatch.setattr(_client, '_SOCKET_PATH', socket_path)
            assert _client.get('/v2/snaps/hello-world') == {'foo': 'bar'}

    def test_a_healthy_socket_still_works(self, monkeypatch: pytest.MonkeyPatch):
        # The control: the same fake snapd answering properly goes through the untouched path.
        with _snapd_that('ok') as socket_path:
            monkeypatch.setattr(_client, '_SOCKET_PATH', socket_path)
            assert _client.get('/v2/snaps/hello-world') == {'foo': 'bar'}


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
        assert exc_info.value._kind == 'charmlibs-snap-change-error'
        assert exc_info.value.message == 'install failed'  # Taken from the 'err' field.
        assert exc_info.value._value == '42'  # The change id.

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
        assert exc_info.value._response == []

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
            ConnectionError('connection refused'),
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
            ConnectionError('connection refused'),
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
        assert exc_info.value._kind == 'charmlibs-snap-change-unknown'
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
        with pytest.raises(APIError) as exc_info:
            _client.get_logs(query={'n': 10, 'names': 'hello-world'})
        assert exc_info.value._kind == 'app-not-found'

    def test_logs_malformed_response_raises_bad_response_error(self, mock_raw: MagicMock):
        mock_raw.return_value = _fake_response(b'some-bytes', url='http://foo/some-path')
        with pytest.raises(BadResponseError) as exc_info:
            _client.get_logs(query={'n': 10, 'names': 'lxd'})
        assert 'Invalid JSON' in exc_info.value.message
        assert 'some-path' in exc_info.value.message
        assert exc_info.value._response == 'some-bytes'


def test_all_errors_mapped():
    unmapped = {
        # Base classes
        'Error',
        'APIError',
        # Transport errors
        'ConnectionError',
        'SocketNotFoundError',
        'TimeoutError',
        # Manually raised errors
        'BadResponseError',
        'ChangeError',
    }
    unmapped = unmapped | {
        # Narrowed from _NotFoundError by the function that made the request, never mapped from a
        # kind: snapd has no kind that means "the store doesn't have it" as opposed to "it isn't
        # installed". See _NotFoundError and test_absent_snap_kinds below.
        'NotInStoreError',
    }
    expected = {
        name
        for name in dir(charmlibs.snap._errors)
        if name.endswith('Error') and name not in unmapped
    }
    # A set, not a sorted list: a type may be reached by more than one kind.
    actual = {cls.__name__ for cls in _client._ERRORS.values()}
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
        assert exc._kind == result.get('kind', '')
        assert exc._value == result.get('value', '')
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
        assert exc_info.value._kind == 'charmlibs-snap-change-error'
        assert exc_info.value.message == change['err']  # Message comes from the 'err' field.
        assert exc_info.value._value == str(async_envelope['change'])  # The polled change id.
