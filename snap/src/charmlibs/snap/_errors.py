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

"""Logical error types for responses from the snapd API."""

from __future__ import annotations

import builtins as _builtins
import typing

if typing.TYPE_CHECKING:
    from typing_extensions import Self


class Error(Exception):
    """Base class for all library errors, not raised directly."""

    def __init__(self, message: str):
        super().__init__(message)
        self._message = message

    @property
    def message(self) -> str:
        """The error message, typically from the snapd API response."""
        return self._message

    def __repr__(self) -> str:
        return f'{type(self).__module__}.{type(self).__name__}({self.message!r})'


#####################################################
# Errors raised when communicating with snapd fails #
#####################################################


class BadResponseError(Error):
    """Raised manually when the snapd API returns a response we don't understand.

    Callers will not be able to resolve this error directly. It means the library and snapd
    disagree about the shape of a response, so it should be reported to the library maintainers.
    The error message includes what snapd sent that the library could not read, so an uncaught
    traceback carries everything the report needs.

    Use :attr:`message` rather than ``str(error)`` for a charm's status, which is truncated for
    display and has no room for a response body.
    """

    def __init__(self, message: str, *, response: object = None):
        super().__init__(message)
        # What snapd sent that we couldn't read: a string for a response that wasn't valid JSON,
        # or the decoded JSON value for one that was well-formed but not what we expected. None
        # when the message says all there is to say, as for an unexpected redirect. Private:
        # callers can't act on it, they can only include it in a bug report.
        self._response = response

    def __str__(self) -> str:
        # A traceback renders an exception as `type(error): str(error)`, so this is the only
        # channel that reaches a bug report when a charm doesn't catch the error. Newlines are
        # safe: juju keeps a multi-line log record intact rather than splitting it.
        if self._response is None:
            return self._message
        return f'{self._message} -- response:\n{self._response!r}'

    def __repr__(self) -> str:
        response = '' if self._response is None else f', response={self._response!r}'
        return f'{type(self).__module__}.{type(self).__name__}({self.message!r}{response})'


class ConnectionError(Error, _builtins.ConnectionError):  # noqa: A001 (shadowing a Python builtin)
    """Raised when a connection to the snapd socket fails.

    This typically indicates that snapd isn't running -- for example, it may be restarting
    as part of a snap operation. The library briefly retries read-only requests before giving
    up, so a caller that sees this error is looking at a system where snapd stayed unreachable.
    Requests that change state aren't retried, since the library can't tell whether snapd
    received them.

    See :class:`SocketNotFoundError` for the case where the socket doesn't exist at all.
    """


class SocketNotFoundError(ConnectionError):
    """Raised when the snapd socket does not exist.

    This typically indicates that snapd is not installed on the system. Unlike other connection
    failures, this is not retried: a socket that isn't there won't appear moments later.
    """


class TimeoutError(Error, _builtins.TimeoutError):  # noqa: A001 (shadowing a Python builtin)
    """Raised when snapd does not respond to a request in time.

    This typically indicates that snapd is waiting on the snap store, which may indicate
    a transient issue with the store or a problem with the system's network connection.
    Callers may want to catch this for retry logic or to surface a user-friendly message.
    """


##############################################
# Errors raised from snapd's error responses #
##############################################


class APIError(Error):
    """Raised when the snapd API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        value: object,
        status_code: int | None = None,
        status: str | None = None,
    ):
        super().__init__(message)
        self._kind = kind
        self._value = value
        self._status_code = status_code
        self._status = status

    @classmethod
    def _from(cls, error: APIError) -> Self:
        return cls(
            error._message,
            kind=error._kind,
            value=error._value,
            status_code=error._status_code,
            status=error._status,
        )

    def __str__(self) -> str:
        # Surface `value` when it adds information the message doesn't already carry.
        # Most useful for _NotFoundError, with message 'snap not installed' and value '<snap>'.
        # Skip OptionNotFoundError's non-string value, which is redundant with its message.
        value = self._value
        if isinstance(value, str) and value and value not in self._message:
            return f'{self._message} ({value})'
        return self._message

    def __repr__(self) -> str:
        return (
            f'{type(self).__module__}.{type(self).__name__}('
            f'{self.message!r}'
            f', kind={self._kind!r}'
            f', value={self._value!r}'
            f', status_code={self._status_code!r}'
            f', status={self._status!r}'
            ')'
        )


class _AlreadyInstalledError(APIError):  # pyright: ignore[reportUnusedClass]
    """Raised via the API when an install is attempted for a snap that is already installed."""


class AppNotFoundError(APIError):
    """Raised via the API when a specified app is not found within an installed snap."""


class _NotFoundError(APIError):
    """Raised via the API when a snap is not found.

    Internal only: callers must narrow to either NotInstalledError or NotInStoreError.
    """


class NotInstalledError(_NotFoundError):
    """Raised when a snap is not installed on the system."""


class NotInStoreError(_NotFoundError):
    """Raised when the snap store has no snap by that name.

    Distinct from :class:`ChannelNotAvailableError` and :class:`RevisionNotAvailableError`.
    """


class NeedsClassicError(APIError):
    """Raised via the API if classic is not specified for a classic confinement snap.

    This can occur for a snap install or refresh.
    """


class ChannelNotAvailableError(APIError):
    """Raised via the API when no snap revision is available on the specified channel."""


class RevisionNotAvailableError(APIError):
    """Raised via the API when the specified snap revision is not available."""


class _NoUpdatesAvailableError(APIError):  # pyright: ignore[reportUnusedClass]
    """Raised via the API when a refresh is attempted but no updates are available."""


class _InterfacesUnchangedError(APIError):  # pyright: ignore[reportUnusedClass]
    """Raised via the API when a connect/disconnect would result in no change.

    This class is private because the public disconnect function suppresses this error,
    following the snap CLI's lead.
    """


class OptionNotFoundError(APIError):
    """Raised via the API when the specified snap config option is not found."""


class ChangeError(APIError):
    """Raised when a snap change results in an error or has an unexpected status."""
