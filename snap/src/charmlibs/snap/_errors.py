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

import builtins as _builtins


class Error(Exception):
    """Base class for all library errors, not raised directly.

    Args:
        message: Typically the 'message' field from a snapd API response.
        kind: The 'kind' field from a snapd API response, used to derive the specific error type.
            Manually constructed errors have the kind 'charmlibs-snap'.
        value: The 'value' field from a snapd API response, which may contain additional details.
            Almost always a string, but can be any JSON value.
        status_code: The HTTP status code from the snapd API response, if applicable.
            Stored privately for logging and debugging, not part of the public error API.
        status: The 'status' field from a snapd API response, if applicable.
            Stored privately for logging and debugging, not part of the public error API.
    """

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
        # Exposed publicly as read-only properties.
        self._message = message
        self._kind = kind
        self._value = value
        # Too low-level to be part of the public API, but useful for debugging and logging.
        self._status_code = status_code
        self._status = status

    @property
    def message(self) -> str:
        """The error message, typically from the snapd API response."""
        return self._message

    @property
    def kind(self) -> str:
        """The error kind, typically from the snapd API response."""
        return self._kind

    @property
    def value(self) -> object:
        """The error value, typically from the snapd API response.

        Currently a string, but future library versions may return any ``object`` subtype.
        """
        return str(self._value)

    def __repr__(self) -> str:
        return (
            f'{type(self).__module__}.{type(self).__name__}('
            f'{self.message!r}'
            f', kind={self.kind!r}'
            f', value={self.value!r}'
            f', status_code={self._status_code!r}'
            f', status={self._status!r}'
            ')'
        )


#####################################################
# Errors raised when communicating with snapd fails #
#####################################################


class BadResponseError(Error):
    """Raised manually when the snapd API returns a response we don't understand.

    Callers will not be able to resolve this error directly, but may want to catch it for logging,
    or to trigger retries. If retries are not successful, user intervention may be required.
    """


class ConnectionError(Error, _builtins.ConnectionError):  # noqa: A001 (shadowing a Python builtin)
    """Raised when a connection to the snapd socket fails.

    This typically indicates that snapd is not installed or running.
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


class _AlreadyInstalledError(APIError):  # pyright: ignore[reportUnusedClass]
    """Raised via the API when an install is attempted for a snap that is already installed."""


class AppNotFoundError(APIError):
    """Raised via the API when a specified app is not found within an installed snap."""


class NotFoundError(APIError):
    """Raised via the API when a snap is not found in the store."""


class NotInstalledError(APIError):
    """Raised via the API when a snap is not installed on the system."""


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
    """Raised via the API when the specified snap config option is not found.

    ``OptionNotFoundError.value`` looks like ``"{'SnapName': 'hello-world', 'Key': 'foo'}"``.
    """


class ChangeError(APIError):
    """Raised when a snap change results in an error or has an unexpected status."""
