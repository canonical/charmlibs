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

"""Representations of the system's Snaps, and abstractions around managing them.

The ``snap`` package provides convenience methods for listing, installing, refreshing, and removing
Snap packages, in addition to setting and getting configuration options for them.

In the ``snap`` package, ``SnapCache`` creates a ``dict``-like mapping of ``Snap`` objects when
instantiated. Installed snaps are fully populated, and available snaps are lazily-loaded upon
request. This module relies on an installed and running ``snapd`` daemon to perform operations over
the ``snapd`` HTTP API.

``SnapCache`` objects can be used to install or modify nnap packages by name in a manner similar to
using the ``snap`` command from the commandline.

An example of adding Juju to the system with ``SnapCache`` and setting a config value::

    try:
        cache = snap.SnapCache()
        juju = cache["juju"]

        if not juju.present:
            juju.ensure(snap.SnapState.Latest, channel="beta")
            juju.set({"some.key": "value", "some.key2": "value2"})
    except snap.SnapError as e:
        logger.error("An exception occurred when installing charmcraft. Reason: %s", e.message)

In addition, the ``snap`` module provides "bare" methods which can act on Snap packages as
simple function calls. :meth:`add`, :meth:`remove`, and :meth:`ensure` are provided, as
well as :meth:`add_local` for installing directly from a local ``.snap`` file. These return
``Snap`` objects.

As an example of installing several Snaps and checking details::

    try:
        nextcloud, charmcraft = snap.add(["nextcloud", "charmcraft"])
        if nextcloud.get("mode") != "production":
            nextcloud.set({"mode": "production"})
    except snap.SnapError as e:
        logger.error("An exception occurred when installing snaps. Reason: %s" % e.message)
"""

from ._snap import (
    Error,
    JSONAble,
    JSONType,
    MetaCache,
    Snap,
    SnapAPIError,
    SnapCache,
    SnapClient,
    SnapError,
    SnapNotFoundError,
    SnapService,
    SnapServiceDict,
    SnapState,
    add,
    ansi_filter,
    ensure,
    hold_refresh,
    install_local,
    remove,
)
from ._version import __version__ as __version__

__all__ = [
    'Error',
    'JSONAble',
    'JSONType',
    'MetaCache',
    'Snap',
    'SnapAPIError',
    'SnapCache',
    'SnapClient',
    'SnapError',
    'SnapNotFoundError',
    'SnapService',
    'SnapServiceDict',
    'SnapState',
    'add',
    'ansi_filter',
    'ensure',
    'hold_refresh',
    'install_local',
    'remove',
]
