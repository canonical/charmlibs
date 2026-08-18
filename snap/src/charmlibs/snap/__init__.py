# Copyright 2025 Canonical Ltd.
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

"""Opinionated library for performing snap operations, targeted at use in charm code.

Use :func:`ensure_installed` to ensure that a snap is installed, optionally on a specific
channel or revision.

Manually manage snap installation with :func:`install`, :func:`refresh`, and :func:`remove`.
Use :func:`list_one` to query the current state of an installed snap.

Also manage:

- Automatic refreshes with :func:`hold` and :func:`unhold`.
- Services with :func:`start`, :func:`stop`, and :func:`restart`.
- Config with :func:`get`, :func:`get_one`, :func:`set`, and :func:`unset`.
- Connections between snaps with :func:`connect` and :func:`disconnect`.
- Application aliases with :func:`alias` and :func:`unalias`.

Exceptions
----------

All errors raised due to interactions with the snapd API are subclasses of :class:`Error`.
Callers may trigger regular Python exceptions (e.g. :class:`ValueError`) when passing
invalid arguments to library functions.

All functions will raise a :class:`APIError` (or a subclass) if snapd returns an error response.
Functions will raise specific subclasses where possible to allow callers to handle logical errors.
Check the documentation for each function for details on which exceptions it may raise. A
function's documented errors are the ones it can report specifically: a plain :class:`APIError`,
or one of the transport errors below, is possible for any call.

Separately from the :class:`APIError` hierarchy (but inheriting from :class:`Error`),
the library may also raise the following exceptions:

A :class:`TimeoutError` indicates that snapd did not respond to a request in time. The library
does not retry a request that timed out: the timeout is generous, and already covers the retries
snapd itself makes against the store within a single request. The failure may still be transient,
due to the snap store infrastructure being under load, so callers may catch this error to layer
their own retry logic on top, or report a transient failure to the user.

A :class:`ConnectionError` indicates that snapd could not be reached at all, and may require user
action. The library briefly retries read-only requests, since snapd may be restarting as part of
a snap operation, but not requests that change state, since it cannot tell whether snapd received
them. :class:`SocketNotFoundError`, a subclass raised when the snapd socket does not exist, is
never retried: it usually means snapd is not installed on the system.

A :class:`BadResponseError` is raised if the snapd API returns a response the library does not
understand. Callers will not be able to resolve this error directly, and should report it to the
library maintainers, along with the error's :func:`repr`, which includes what snapd sent that the
library could not read.
"""

from ._errors import (
    APIError,
    AppNotFoundError,
    BadResponseError,
    ChangeError,
    ChannelNotAvailableError,
    ConnectionError,  # noqa: A004 (shadowing a Python builtin)
    Error,
    NeedsClassicError,
    NotInstalledError,
    NotInStoreError,
    OptionNotFoundError,
    RevisionNotAvailableError,
    SocketNotFoundError,
    TimeoutError,  # noqa: A004 (shadowing a Python builtin)
)
from ._functions import (
    ensure_installed,
)
from ._snapd_aliases import (
    alias,
    unalias,
)
from ._snapd_apps import (
    restart,
    start,
    stop,
)
from ._snapd_conf import (
    get,
    get_one,
    set,  # noqa: A004 (shadowing a Python builtin)
    unset,
)
from ._snapd_interfaces import (
    connect,
    disconnect,
)
from ._snapd_logs import (
    LogEntry,
    logs,
)
from ._snapd_snaps import (
    InstalledInfo,
    hold,
    install,
    list_one,
    refresh,
    remove,
    unhold,
)
from ._version import __version__ as __version__

__all__ = [
    'APIError',
    'AppNotFoundError',
    'BadResponseError',
    'ChangeError',
    'ChannelNotAvailableError',
    'ConnectionError',
    'Error',
    'InstalledInfo',
    'LogEntry',
    'NeedsClassicError',
    'NotInStoreError',
    'NotInstalledError',
    'OptionNotFoundError',
    'RevisionNotAvailableError',
    'SocketNotFoundError',
    'TimeoutError',
    'alias',
    'connect',
    'disconnect',
    'ensure_installed',
    'get',
    'get_one',
    'hold',
    'install',
    'list_one',
    'logs',
    'refresh',
    'remove',
    'restart',
    'set',
    'start',
    'stop',
    'unalias',
    'unhold',
    'unset',
]
