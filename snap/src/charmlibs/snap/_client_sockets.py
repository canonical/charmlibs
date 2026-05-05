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

"""Handle HTTP requests over Unix sockets."""

from __future__ import annotations

import http.client
import socket
import sys
import urllib.request


class _NotProvided:
    pass


_NOT_PROVIDED = _NotProvided()


class _UnixSocketConnection(http.client.HTTPConnection):
    """Implementation of HTTPConnection that connects to a named Unix socket."""

    def __init__(self, host: str, socket_path: str, timeout: _NotProvided | float = _NOT_PROVIDED):
        if isinstance(timeout, _NotProvided):
            super().__init__(host)
        else:
            super().__init__(host, timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        """Override connect to use Unix socket (instead of TCP socket)."""
        if not hasattr(socket, 'AF_UNIX'):
            raise NotImplementedError(f'Unix sockets not supported on {sys.platform}')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._socket_path)
        if not isinstance(self.timeout, _NotProvided):
            self.sock.settimeout(self.timeout)


class UnixSocketHandler(urllib.request.AbstractHTTPHandler):
    """Implementation of HTTPHandler that uses a named Unix socket."""

    def __init__(self, socket_path: str):
        super().__init__()
        self._socket_path = socket_path

    def http_open(self, req: urllib.request.Request):
        """Override http_open to use a Unix socket connection (instead of TCP)."""
        return self.do_open(
            _UnixSocketConnection,  # type:ignore -- we don't implement all the optional init args
            req,
            socket_path=self._socket_path,
        )
