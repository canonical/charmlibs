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


class SnapError(Exception):
    """Base class for all library errors, raised directly when a more specific type isn't defined.

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
        status_code: int | None,
        status: str | None,
    ):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.value = value
        # Too low-level to be part of the public API, but useful for debugging and logging.
        self._status_code = status_code
        self._status = status

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}('
            f'{self.message!r}'
            f', kind={self.kind!r}'
            f', value={self.value!r}'
            f', status_code={self._status_code!r}'
            f', status={self._status!r}'
            ')'
        )


class SnapAPIError(SnapError):
    """Raised manually when the snapd API returns a response we don't understand.

    Callers will not be able to resolve this error directly, but may want to catch it for logging,
    or to trigger retries. If retries are not successful, user intervention may be required.
    """


class SnapAlreadyInstalledError(SnapError):
    """Raised via the API when an install is attempted for a snap that is already installed."""


class SnapAppNotFoundError(SnapError):
    """Raised via the API when a specified app is not found within an installed snap."""


class SnapNotFoundError(SnapError):
    """Raised when a snap is not found, either in the store or as an installed snap."""


class SnapNeedsClassicError(SnapError):
    """Raised via the API if classic is not specified for a classic confinement snap.

    This can occur for a snap install or refresh.
    """


class _SnapNoUpdatesAvailableError(SnapError):
    """Raised via the API when a refresh is attempted but no updates are available.

    This class is private because the public refresh function suppresses this error,
    following the snap CLI's lead.
    """


class _SnapInterfacesUnchangedError(SnapError):
    """Raised via the API when a connect/disconnect would result in no change.

    This class is private because the public disconnect function suppresses this error,
    following the snap CLI's lead.
    """


class SnapOptionNotFoundError(SnapError):
    """Raised via the API when the specified snap config option is not found.

    Note that ``SnapOptionNotFoundError.value`` is typically a ``dict``,
    rather than the usual ``str``::

        {'SnapName': snap_name, 'Key': key}.
    """


class SnapChangeError(SnapError):
    """Raised manually when a snap change has an unexpected status (including failures)."""


def _error_type_from_result_kind(kind: str) -> type[SnapError]:  # pyright: ignore[reportUnusedFunction]
    match kind:
        case 'snap-already-installed':
            return SnapAlreadyInstalledError
        case 'app-not-found':
            return SnapAppNotFoundError
        case 'option-not-found':
            return SnapOptionNotFoundError
        case 'snap-needs-classic':
            return SnapNeedsClassicError
        case 'snap-not-found' | 'snap-not-installed':
            return SnapNotFoundError
        case 'snap-no-update-available':
            return _SnapNoUpdatesAvailableError
        case 'interfaces-unchanged':
            return _SnapInterfacesUnchangedError
        case _:
            return SnapError
