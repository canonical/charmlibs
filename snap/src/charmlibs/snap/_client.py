# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Get, post, and put requests to the snapd REST API.

Synchronous results are returned directly, as basic Python types decoded from JSON.
Async operations are waited on until completion and then the final result is returned.
Errors are converted into :class:`Error` exceptions, with specific subclasses where possible.
"""

from __future__ import annotations

import json
import logging
import time
import typing
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import _client_sockets, _errors

if typing.TYPE_CHECKING:
    import http.client

logger = logging.getLogger(__name__)

# Defined in the snap application itself under dirs/dirs.go as SnapdSocket.
_SOCKET_PATH = '/run/snapd.socket'
# Timeout for a single request.
# Defined as the default for the snap CLI in client/client.go as doTimeout.
# snapd may spend up to 38s retrying store lookups within a single request.
# The client timeout must not be shorter than that, or we'll give up before snapd does.
_REQUEST_TIMEOUT = 120
# snapd may be briefly unreachable during a daemon restart.
# The snap CLI retries GET connection failures for up to doTimeout (120s)
# at doRetry intervals (250ms).
# We use a shorter budget (matching the change-poller's maxGoneTime in cmd/snap/wait.go)
# to avoid waiting too long when snapd is unreachable (we still allow 120s for timeouts).
_CONNECTION_RETRY_BUDGET = 5
_CONNECTION_RETRY_INTERVAL = 0.25
# Spacing between successful change polls, matching the snap CLI's pollTime (cmd/snap/wait.go).
_POLL_INTERVAL = 0.1


def get(path: str, query: dict[str, Any] | None = None):
    """GET request to snapd REST API."""
    response = _retry_json_get(path, query=query)
    result = _decode(response)
    return _resolve(result)


def get_logs(query: dict[str, Any] | None = None):
    """GET request to /v2/logs endpoint, which returns a stream of log entries."""
    response = _retry_json_get('/v2/logs', query=query)
    return _decode_logs(response)


def post(path: str, body: dict[str, Any] | None = None):
    """POST request to snapd REST API."""
    response = _json_request('POST', path, body=body)
    result = _decode(response)
    return _resolve(result)


def put(path: str, body: dict[str, Any] | None = None):
    """PUT request to snapd REST API."""
    response = _json_request('PUT', path, body=body)
    result = _decode(response)
    return _resolve(result)


def _retry_json_get(
    path: str, *, query: dict[str, Any] | None = None, log: bool = True
) -> http.client.HTTPResponse:
    """Make a GET request to snapd, retrying transient connection failures.

    See :data:`_CONNECTION_RETRY_BUDGET`. The decoding of the response is left to the caller so
    that only the request itself is retried.
    """
    deadline = time.monotonic() + _CONNECTION_RETRY_BUDGET
    while True:
        try:
            return _json_request('GET', path, query=query, log=log)
        except _errors.ConnectionError as e:  # noqa: PERF203
            # We don't catch TimeoutError -- the timeout is longer than our retry budget.
            # We don't retry on a missing socket, since that means snapd is not running at all.
            if e.kind == 'charmlibs-snap-socket-not-found':
                raise
            if time.monotonic() > deadline:
                raise
            time.sleep(_CONNECTION_RETRY_INTERVAL)


def _json_request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    log: bool = True,
) -> http.client.HTTPResponse:
    """Make a JSON request to snapd, returning the raw HTTPResponse.

    If query dict is provided, it is encoded and appended as a query string
    to the URL. If body dict is provided, it is serialised as JSON and used
    as the HTTP body (with Content-Type: "application/json").
    """
    if log:
        logger.debug('_request(%r, %r, query=%r, body=%r)', method, path, query, body)
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        data = None
    return _request(method, path, query=query, headers=headers, data=data)


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    data: bytes | None = None,
) -> http.client.HTTPResponse:
    """Make a raw request to the snapd server; return the HTTPResponse object."""
    query_str = f'?{urllib.parse.urlencode(query, doseq=True)}' if query else ''
    request = urllib.request.Request(
        f'http://localhost/{path.lstrip("/")}{query_str}',
        method=method,
        headers=headers or {},
        data=data,
    )
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_client_sockets.UnixSocketHandler(_SOCKET_PATH))
    opener.add_handler(urllib.request.HTTPRedirectHandler())
    # We need to handle HTTP errors ourselves, since the response body contains meaningful info,
    # so we don't add HTTPErrorProcessor or HTTPDefaultErrorHandler, which would raise too early.
    try:
        return opener.open(request, timeout=_REQUEST_TIMEOUT)
    except TimeoutError:
        raise _errors.TimeoutError(
            f'Request to snapd timed out after {_REQUEST_TIMEOUT}s: {method} {path}',
            kind='charmlibs-snap-request-timeout',
            value='',
        ) from None
    except urllib.error.URLError as e:
        if e.args and isinstance(e.args[0], FileNotFoundError):
            raise _errors.ConnectionError(
                f'Could not connect to snapd: socket not found at {_SOCKET_PATH!r}',
                kind='charmlibs-snap-socket-not-found',
                value='',
            ) from None
        raise _errors.ConnectionError(
            str(e.reason),
            kind='charmlibs-snap-connection-error',
            value='',
        ) from e


def _decode(response: http.client.HTTPResponse) -> object | _Change:
    """Decode a snapd response, raising errors and reifying async changes.

    The response body is decoded from JSON: an async response is returned as a
    :class:`_Change` (which the caller can :meth:`_Change.wait` on), a sync
    response returns its ``result`` field, and an error response raises.
    """
    response_bytes = response.read()
    try:
        response_dict: dict[str, Any] = json.loads(response_bytes)
    except json.JSONDecodeError as e:
        raise _errors.BadResponseError(
            message=f'Invalid JSON in response for path {_get_path(response)!r}: {e}',
            kind='charmlibs-snap',
            value=response_bytes.decode(errors='replace'),
            status_code=response.status,
            status=response.reason,
        ) from None
    if not isinstance(response_dict, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _errors.BadResponseError(
            message=f"Unexpected response type {type(response_dict).__name__!r} for path {_get_path(response)!r}, expected a 'dict'",  # noqa: E501
            kind='charmlibs-snap',
            value=str(response_dict),
            status_code=response.status,
            status=response.reason,
        )
    try:
        match response_dict['type']:
            case 'error':
                raise _make_error(response_dict)
            case 'async':
                return _Change(change_id=response_dict['change'])
            case _:
                return response_dict['result']
    except KeyError as e:
        raise _errors.BadResponseError(
            message=f'Missing expected key {e} in response for path {_get_path(response)!r}',
            kind='charmlibs-snap',
            value=str(response_dict),
            status_code=response.status,
            status=response.reason,
        ) from None


def _decode_logs(response: http.client.HTTPResponse) -> list[dict[str, str]]:
    """Decode the stream of log entries returned by /v2/logs, raising errors.

    Sanitization checks for individual entries are left to the caller.
    """
    response_bytes = response.read()
    # /v2/logs returns a stream of JSON objects separated by \n\x1e
    try:
        logs = [
            json.loads(s)
            for line in response_bytes.split(b'\n\x1e')
            if (s := line.decode().strip())
        ]
    except json.JSONDecodeError as e:
        raise _errors.BadResponseError(
            message=f'Invalid JSON in response for path {_get_path(response)!r}: {e}',
            kind='charmlibs-snap',
            value=response_bytes.decode(errors='replace'),
            status_code=response.status,
            status=response.reason,
        ) from None
    # Error responses are a single JSON object, which we wrapped in a list when decoding.
    if len(logs) == 1 and logs[0].get('type') == 'error':
        raise _make_error(logs[0])
    return logs


def _get_path(response: http.client.HTTPResponse) -> str:
    return urllib.parse.urlparse(response.url).path


##########
# errors #
##########


_ERRORS = {
    'snap-already-installed': _errors._AlreadyInstalledError,
    'app-not-found': _errors.AppNotFoundError,
    'option-not-found': _errors.OptionNotFoundError,
    'snap-channel-not-available': _errors.ChannelNotAvailableError,
    'snap-needs-classic': _errors.NeedsClassicError,
    'snap-not-found': _errors.NotFoundError,
    'snap-not-installed': _errors.NotInstalledError,
    'snap-no-update-available': _errors._NoUpdatesAvailableError,
    'snap-revision-not-available': _errors.RevisionNotAvailableError,
    'interfaces-unchanged': _errors._InterfacesUnchangedError,
}


def _make_error(response: dict[str, Any]) -> _errors.APIError:
    result = response.get('result', {})
    kind = result.get('kind', '')
    error_type = _ERRORS.get(kind, _errors.APIError)
    return error_type(
        result.get('message', ''),
        kind=kind,
        value=result.get('value', ''),
        status_code=response.get('status-code'),
        status=response.get('status'),
    )


###########
# changes #
###########


def _resolve(result: object | _Change):
    """Wait for an async change to complete, or return a synchronous result unchanged."""
    if isinstance(result, _Change):
        return result.wait()
    return result


class _Change:
    def __init__(self, change_id: str):
        self._id = change_id

    def wait(self) -> object:
        """Poll until the change reaches a terminal state, then return its data.

        Like the snap CLI, this places no overall deadline on the change: it polls until the
        change is ``Done``, ``Wait``, or ``Error``.
        """
        logger.debug('Waiting for change [%s]', self._id)
        while True:
            result = self._poll()
            match status := result.get('status'):
                case 'Do' | 'Doing' | 'Undo' | 'Undoing':
                    time.sleep(_POLL_INTERVAL)
                    continue
                case 'Done':
                    return result.get('data', {})
                case 'Wait':
                    # Follow the snap CLI's behavior of treating Wait as a success.
                    # - Log the change ID in case user investigation is required.
                    # - Callers should know in advance if action is expected after a change,
                    #   for example if the system requires a restart.
                    # - The key functions that rely on changes (install, refresh, remove) return
                    #   truthy/falsy values to indicate whether a change was performed. If we need
                    #   to expose the Wait status to callers in future, we can do so with a return
                    #   value rather than an exception.
                    logger.warning("snap change [%s] succeeded with status 'Wait'", self._id)
                    return result.get('data', {})
                case 'Error':
                    raise _errors.ChangeError(
                        message=result.get('err', ''),
                        kind='charmlibs-snap-change-error',
                        value=self._id,
                        status=status,
                    )
                case _:
                    raise _errors.ChangeError(
                        message=f'Unexpected status {status!r} for snap change {self._id}',
                        kind='charmlibs-snap-change-unknown',
                        value=self._id,
                        status=status,
                    )

    def _poll(self):
        response = _retry_json_get(f'/v2/changes/{self._id}', log=False)
        result = _decode(response)
        if not isinstance(result, dict):
            raise _errors.BadResponseError(
                message=f'Unexpected response type {type(result).__name__} while waiting for change {self._id}',  # noqa: E501
                kind='charmlibs-snap',
                value=str(result),
            )
        return typing.cast('dict[str, Any]', result)
