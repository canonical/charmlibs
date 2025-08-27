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

"""Charm interface library for the ``tls_certificates`` interface.

Support for current versions of the interface is available under:

* ``charmlibs.interfaces.tls_certificates.v0``
* ``charmlibs.interfaces.tls_certificates.v1``

tls_certificates.v0
-------------------
.. automodule:: tls_certificates.v0

tls_certificates.v1
-------------------
.. automodule:: tls_certificates.v1
"""

from . import v0, v1

__all__ = [
    'v0',
    'v1',
]
__version__ = '1.0.0'
