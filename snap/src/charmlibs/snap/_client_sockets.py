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
import urllib.request


class _UnixSocketConnection(http.client.HTTPConnection):
    """Implementation of HTTPConnection that connects to a named Unix socket."""

    def __init__(self, host: str, timeout: float, socket_path: str):
        # Only constructed by UnixSocketHandler.http_open, using AbstractHTTPHandler.do_open.
        # do_open(http_class, req, **http_conn_args) passes:
        # - req.host positionally
        # - timeout=req.timeout
        # - all user-supplied http_conn_args
        # We pass socket_path as a keyword argument.
        super().__init__(host, timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        """Override connect to use Unix socket (instead of TCP socket)."""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


class UnixSocketHandler(urllib.request.AbstractHTTPHandler):
    """Implementation of HTTPHandler that uses a named Unix socket."""

    def __init__(self, socket_path: str):
        super().__init__()
        self._socket_path = socket_path

    def http_open(self, req: urllib.request.Request):
        """Override http_open to use a Unix socket connection (instead of TCP)."""
        return self.do_open(
            _UnixSocketConnection,  # type: ignore -- we don't implement all the optional init args
            req,
            socket_path=self._socket_path,
        )
