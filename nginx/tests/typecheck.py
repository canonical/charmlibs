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

"""Type checking statements for Nginx."""

from charmlibs.nginx import Nginx
from charmlibs.nginx.tls_config_mgr import TLSConfig


def typecheck_reconcile_signature_null(nginx: Nginx) -> None:
    nginx.reconcile(upstreams_to_addresses={}, tls_config=None)


def typecheck_reconcile_signature_full(nginx: Nginx) -> None:
    nginx.reconcile(upstreams_to_addresses={'a': {'b', 'c'}}, tls_config=TLSConfig('a', 'b', 'c'))
