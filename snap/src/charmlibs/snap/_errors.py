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

    def __str__(self) -> str:
        # Surface `value` when it adds information the message doesn't already carry.
        # Most useful for NotFoundError, with message 'snap not installed' and value '<snap>'.
        # Skip OptionNotFoundError's non-string value, which is redundant with its message.
        value = self._value
        if isinstance(value, str) and value and value not in self._message:
            return f'{self._message} ({value})'
        return self._message

    @classmethod
    def _narrowed(cls, error: Error) -> Self:
        """Rebuild ``error`` as this more specific type, carrying every field across.

        The client raises the most specific type a response's ``kind`` identifies, which for an
        absent snap is only ever :class:`NotFoundError` -- snapd sends the same kind whether the
        snap is missing from the system or from the store. The function that made the request
        knows which it asked for, so it narrows the error rather than the client guessing. This
        only ever moves down the hierarchy, so the data is carried over unchanged.
        """
        return cls(
            error._message,
            kind=error._kind,
            value=error._value,
            status_code=error._status_code,
            status=error._status,
        )

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
    """Base class for a snap not being where an operation needed it.

    A snap operation can need the snap to be installed on the system, to be offered by the snap
    store, or both. These are independent -- a sideloaded snap is installed but not in the store,
    and a snap withdrawn from the store stays installed -- so the library raises a subclass
    naming which one was missing: :class:`NotInstalledError` or :class:`NotInStoreError`.

    Catch this class to handle both at once, when the distinction doesn't matter. The library
    doesn't raise it directly, so catching a subclass is always enough to be specific.

    snapd doesn't make this distinction itself. It reports an absent snap with the
    ``snap-not-found`` kind, with the ``snap-not-installed`` kind, or as an error with no kind
    at all, depending on the endpoint -- and it uses ``snap-not-found`` for both senses, with
    the same status code and the same ``value``. Only ``message`` differs, so the library
    classifies by which operation was asked for rather than by matching on the message.
    """


class NotInstalledError(NotFoundError):
    """Raised when a snap is not installed on the system.

    Raised by every operation that acts on an installed snap: reading its state or config,
    managing its services, connecting its interfaces, aliasing its apps, holding it, and
    refreshing it.
    """


class NotInStoreError(NotFoundError):
    """Raised when the snap store does not offer a snap by that name.

    Raised by :func:`install`, and by :func:`refresh` for an installed snap the store no longer
    offers. :func:`ensure` can raise it either way. Note this is about the name: a snap that
    exists but has no revision on the requested channel raises
    :class:`ChannelNotAvailableError` instead.
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
    """Raised via the API when the specified snap config option is not found.

    ``OptionNotFoundError.value`` looks like ``"{'SnapName': 'hello-world', 'Key': 'foo'}"``.
    """


class ChangeError(APIError):
    """Raised when a snap change results in an error or has an unexpected status."""
