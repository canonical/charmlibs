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

"""Testing package for ``charmlibs.interfaces.tls_certificates``.

Two independent pieces of API. :class:`RemoteProvider` and :class:`RemoteRequirer` stand in
for the charm on the other end of a ``tls-certificates`` relation, running the charm under
test to build the state; and :func:`mocked` mocks the library's internals for the duration
of a test. Every state-producing call must be made inside a :func:`mocked` scope.

A requirer charm under test is paired with a :class:`RemoteProvider`, and a provider charm
with a :class:`RemoteRequirer` -- the remote plays the opposite role.
"""

from ._mocking import mocked
from ._testing import Outcome, RemoteProvider, RemoteRequirer
from ._version import __version__ as __version__

__all__ = [
    # only the names listed in __all__ are imported when executing:
    # from charmlibs.interfaces.tls_certificates_testing import *
    "Outcome",
    "RemoteProvider",
    "RemoteRequirer",
    "mocked",
]
