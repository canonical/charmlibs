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

r""":mod:`pathlib`-like interface for local and :class:`ops.Container` filesystem paths.

:mod:`apt`

:ref:`Charmhub-hosted libraries <charm-libs-charmhub-hosted>`

The ``pathops`` charm library provides:

- :class:`PathProtocol`: defines the interface of methods common to both local and container paths.
  Use this to type annotate code designed to work on both Kubernetes and machine charms.
- :class:`ContainerPath`: the concrete implementation of the interface for remote paths in the
  workload container of Kubernetes charms. Operations are implemented using the Pebble file API.
- :class:`LocalPath`: the concrete implementation of the interface for local paths, which includes
  both machine charms and the charm container of Kubernetes charms. Inherits from
  :class:`pathlib.PosixPath` and extends the signature of some methods.
- Top-level helper functions such as :func:`ensure_contents`, which operate on both container
  and local paths.

:class:`ContainerPath` methods that interact with the remote filesystem will raise a
:class:`PebbleConnectionError` if the workload container isn't reachable.
Methods designed to work with both local and container paths may handle this error internally,
or they may leave handling connection errors to the caller, documenting this if so.
"""

from __future__ import annotations

from pathlib import Path as _Path  # for __version__

from ops.pebble import ConnectionError as PebbleConnectionError

from ._container_path import ContainerPath, RelativePathError
from ._functions import ensure_contents
from ._local_path import LocalPath
from ._types import PathProtocol

__all__ = (
    'ContainerPath',
    'LocalPath',
    'PathProtocol',
    'PebbleConnectionError',
    'RelativePathError',
    'ensure_contents',
)

__version__ = (_Path(__file__).parent / '_version.txt').read_text().strip()
