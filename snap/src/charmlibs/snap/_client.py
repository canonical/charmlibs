# Copyright 2021 Canonical Ltd.
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
Errors are converted into :class:`SnapError` exceptions, with specific subclasses where possible.
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
    from collections.abc import Generator

logger = logging.getLogger(__name__)

# we need the powerful snapd socket
# defined in the snap application itself under dirs/dirs.go as SnapdSocket
_SOCKET_PATH = '/run/snapd.socket'
# TODO: a user facing way to set timeout? e.g. charmlibs.snap.set_timeouts(request=60, change=1800)
_REQUEST_TIMEOUT = 30
_CHANGE_TIMEOUT = 600  # 10 minutes in seconds


def get(path: str, query: dict[str, Any] | None = None):
    """GET request to snapd REST API."""
    return _request('GET', path, query=query)


def post(path: str, body: dict[str, Any] | None = None):
    """POST request to snapd REST API."""
    return _request('POST', path, body=body)


def put(path: str, body: dict[str, Any] | None = None):
    """PUT request to snapd REST API."""
    return _request('PUT', path, body=body)


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    log: bool = True,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Make a JSON request to the snapd server with the given HTTP method and path.

    If query dict is provided, it is encoded and appended as a query string
    to the URL. If body dict is provided, it is serialied as JSON and used
    as the HTTP body (with Content-Type: "application/json"). The resulting
    body is decoded from JSON.
    """
    if log:
        logger.debug('_request(%r, %r, query=%r, body=%r)', method, path, query, body)
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        data = None
    response = _request_raw(method, path, query=query, headers=headers, data=data)
    response_bytes = response.read()
    try:
        # /v2/logs returns a stream of JSON objects separated by \n\x1e
        if path == '/v2/logs':
            logs = [
                json.loads(s)
                for line in response_bytes.split(b'\n\x1e')
                if (s := line.decode().strip())
            ]
            if len(logs) == 1 and logs[0].get('type') == 'error':
                # still a stream as above but only a single object; like this:
                # [{'type': 'error',
                #  'status-code': 404,
                #  'status': 'Not Found',
                #  'result': {'message': 'snap "code" has no services',
                #   'kind': 'app-not-found'}}]
                response_dict = logs[0]
            else:
                return logs
        # otherwise we expect a single JSON object
        response_dict: dict[str, Any] = json.loads(response_bytes)
    except json.JSONDecodeError as e:
        raise _errors.SnapBadResponseError(
            message=f'Invalid JSON in response for path {path!r}: {e}',
            kind='charmlibs-snap',
            value=response_bytes.decode(errors='replace'),
            status_code=response.status,
            status=response.reason,
        ) from None
    if not isinstance(response_dict, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _errors.SnapBadResponseError(
            message=f"Unexpected response type {type(response_dict).__name__!r} for path {path!r}, expected a 'dict'",  # noqa: E501
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
                return _wait_for_change(change_id=response_dict['change'])
            case _:
                return response_dict['result']
    except KeyError as e:
        raise _errors.SnapBadResponseError(
            message=f'Missing expected key {e} in response for path {path!r}',
            kind='charmlibs-snap',
            value=str(response_dict),
            status_code=response.status,
            status=response.reason,
        ) from None


def _request_raw(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    data: bytes | Generator[bytes, Any, Any] | None = None,
) -> http.client.HTTPResponse:
    """Make a request to the snapd server; return the raw HTTPResponse object."""
    assert path.startswith('/')
    request = urllib.request.Request(
        f'http://localhost{path}'
        + (f'?{urllib.parse.urlencode(query, doseq=True)}' if query else ''),
        method=method,
        headers=headers or {},
        data=data,
    )
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_client_sockets.UnixSocketHandler(_SOCKET_PATH))
    opener.add_handler(urllib.request.HTTPRedirectHandler())
    # We need to handle HTTP errors ourselves, since the response body contains meaningful info.
    # opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    # opener.add_handler(urllib.request.HTTPErrorProcessor())
    try:
        return opener.open(request, timeout=_REQUEST_TIMEOUT)
    except TimeoutError:
        raise _errors.SnapTimeoutError(
            f'Request to snapd timed out after {_REQUEST_TIMEOUT}s: {method} {path}',
            kind='charmlibs-snap-request-timeout',
            value='',
            status_code=None,
            status=None,
        ) from None
    except urllib.error.URLError as e:
        if e.args and isinstance(e.args[0], FileNotFoundError):
            raise _errors.SnapConnectionError(
                f'Could not connect to snapd: socket not found at {_SOCKET_PATH!r}',
                kind='charmlibs-snap-socket-not-found',
                value='',
                status_code=None,
                status=None,
            ) from None
        raise _errors.SnapConnectionError(
            str(e.reason),
            kind='charmlibs-snap-connection-error',
            value='',
            status_code=None,
            status=None,
        ) from e


def _wait_for_change(change_id: str) -> dict[str, Any]:
    """Wait for an async change to complete.

    The poll time is 100 milliseconds, the same as in snap clients.
    """
    logger.debug('_wait_for_change(%r)', change_id)
    deadline = time.monotonic() + _CHANGE_TIMEOUT
    while True:
        if time.monotonic() > deadline:
            raise _errors.SnapTimeoutError(
                f'Timed out after {_CHANGE_TIMEOUT}s waiting for snap change {change_id}',
                kind='charmlibs-snap-change-timeout',
                value='',
                status_code=None,
                status=None,
            )
        response = _request('GET', f'/v2/changes/{change_id}', log=False)
        if not isinstance(response, dict):
            raise _errors.SnapBadResponseError(
                message=f'Unexpected response type {type(response).__name__} while waiting for change {change_id}',  # noqa: E501
                kind='charmlibs-snap',
                value=str(response),
                status_code=None,
                status=None,
            )
        match response.get('status'):
            case 'Do' | 'Doing':
                time.sleep(0.1)
                continue
            case 'Done':
                return response.get('data', {})
            case 'Wait':
                logger.warning("snap change %s succeeded with status 'Wait'", change_id)
                return response.get('data', {})
            case _:  # Including the specific 'Error' status.
                raise _errors.SnapChangeError(
                    message=response.get('err', ''),
                    kind='charmlibs-snap-change-error',
                    value=response.get('id', ''),
                    status_code=None,
                    status=response.get('status'),
                )


def _make_error(response: dict[str, Any]) -> _errors.SnapError:
    result = response.get('result', {})
    kind = result.get('kind', '')
    error_type = _errors._error_type_from_result_kind(kind)
    return error_type(
        result.get('message', ''),
        kind=kind,
        value=result.get('value', ''),
        status_code=response.get('status-code'),
        status=response.get('status'),
    )
